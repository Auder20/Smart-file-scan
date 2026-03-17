from __future__ import annotations

import hashlib
import os
import logging
import random
import multiprocessing
import platform
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

from app.models.file_info import FileInfo, DuplicateGroup

logger = logging.getLogger(__name__)

_CHUNK_SIZE   = 8 * 1024   # 8KB por chunk al leer archivos grandes
_PARTIAL_SIZE = 4 * 1024   # 4KB para el hash de pre-filtrado


def find_duplicates_from_sqlite(
    scan_id: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    max_files: int = 30_000,
    chunk_size: int = 5000,
) -> list[DuplicateGroup]:
    """FEAT 5: Find duplicates by processing files in chunks from SQLite"""
    from app.db.database import get_files_paginated
    
    logger.info(f"Finding duplicates for scan {scan_id} using SQLite chunk processing")
    
    # Get total file count first
    first_page = get_files_paginated(scan_id, 1, 1)
    total_files = first_page['total_files']
    
    if total_files < 2:
        return []
    
    # If too many files, warn and limit
    if total_files > max_files:
        logger.warning(f"Too many files ({total_files:,}), limiting to {max_files:,}")
        total_files = max_files
    
    # Process files in chunks to avoid memory issues
    all_files = []
    processed_files = 0
    
    page = 1
    while processed_files < total_files:
        # Get chunk of files from SQLite
        actual_chunk_size = min(chunk_size, total_files - processed_files)
        paginated_result = get_files_paginated(scan_id, page, actual_chunk_size)
        
        # Convert dict to FileInfo objects
        chunk_files = []
        for file_data in paginated_result['files']:
            file_info = FileInfo(
                name=file_data['name'],
                path=file_data['path'],
                size=file_data['size'],
                extension=file_data.get('extension', ''),
                category=file_data.get('category', ''),
                modified=file_data.get('modified', '')
            )
            chunk_files.append(file_info)
        
        # Process chunk for duplicates
        chunk_duplicates = _find_duplicates_in_chunk(chunk_files, progress_callback)
        all_files.extend(chunk_files)
        
        processed_files += len(chunk_files)
        page += 1
        
        if progress_callback:
            progress_callback(processed_files, total_files)
        
        logger.debug(f"Processed chunk {page-1}: {len(chunk_files)} files, total: {processed_files}")
    
    # Now find duplicates across all processed files
    return find_duplicates(all_files, progress_callback, max_files)


def _find_duplicates_in_chunk(
    files: list[FileInfo],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[FileInfo]:
    """Process a chunk of files to identify potential duplicates by size"""
    if len(files) < 2:
        return files
    
    # Group by size - only keep files that have size duplicates
    by_size: dict[int, list[FileInfo]] = defaultdict(list)
    for f in files:
        if f.size > 0:
            by_size[f.size].append(f)
    
    # Keep only files that have potential duplicates by size
    candidates = []
    for size, size_group in by_size.items():
        if len(size_group) >= 2:
            candidates.extend(size_group)
    
    logger.debug(f"Chunk processing: {len(files)} files -> {len(candidates)} potential duplicates")
    return candidates


def find_duplicates(
    files: list[FileInfo],
    progress_callback: Optional[Callable[[int, int], None]] = None,
    max_files: int = 30_000,
) -> list[DuplicateGroup]:

    if len(files) < 2:
        return []

    # Si hay demasiados archivos, hacer muestreo aleatorio
    if len(files) > max_files:
        logger.warning(f"Demasiados archivos ({len(files):,}), muestreando {max_files:,} para análisis de duplicados")
        files = random.sample(files, max_files)

    # ── Fase 1: agrupar por tamaño ────────────────────────────────────────
    # Archivos con tamaño único NO pueden ser duplicados
    by_size: dict[int, list[FileInfo]] = defaultdict(list)
    for f in files:
        if f.size > 0:
            by_size[f.size].append(f)

    candidates = [g for g in by_size.values() if len(g) >= 2]

    if not candidates:
        return []

    # ── Fase 2: hash parcial (primeros 4KB) ───────────────────────────────
    flat = [f for group in candidates for f in group]
    # path_to_file: mapeo rápido path → FileInfo para reconstruir después del hash
    path_to_file = {f.path: f for f in flat}
    partial_hashes = _compute_hashes_parallel(flat, partial=True)

    by_partial: dict[str, list[FileInfo]] = defaultdict(list)
    for file_path, ph in partial_hashes.items():
        if ph and file_path in path_to_file:
            by_partial[ph].append(path_to_file[file_path])

    candidates2 = [g for g in by_partial.values() if len(g) >= 2]

    if not candidates2:
        return []

    # ── Fase 3: hash completo SHA-256 ─────────────────────────────────────
    flat2 = [f for group in candidates2 for f in group]
    path_to_file2 = {f.path: f for f in flat2}
    full_hashes = _compute_hashes_parallel(flat2, partial=False, callback=progress_callback)

    by_full: dict[str, list[FileInfo]] = defaultdict(list)
    for file_path, fh in full_hashes.items():
        if fh and file_path in path_to_file2:
            fi = path_to_file2[file_path]
            # Guardar el hash en el objeto (necesario para _build_group)
            try:
                fi.hash = fh
            except Exception:
                pass  # Si el modelo es frozen, ignorar
            by_full[fh].append(fi)

    groups = [
        _build_group(hash_val, group_files)
        for hash_val, group_files in by_full.items()
        if len(group_files) >= 2
    ]

    return sorted(groups, key=lambda g: g.wasted_size, reverse=True)


def _compute_hashes_parallel(
    files: list[FileInfo],
    partial: bool,
    callback: Optional[Callable[[int, int], None]] = None,
    max_workers: int = min(multiprocessing.cpu_count() * 2, 8),
) -> dict[str, Optional[str]]:
    """Retorna dict[path, hash] para evitar usar FileInfo como key de dict
    (Python 3.14 + Pydantic v2: los modelos no son hasheables por defecto)."""

    results: dict[str, Optional[str]] = {}
    completed = 0
    total     = len(files)
    hash_func = _partial_hash if partial else _full_hash

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(hash_func, f.path): f.path
            for f in files
        }

        for future in as_completed(future_to_path):
            file_path = future_to_path[future]
            try:
                results[file_path] = future.result()
            except Exception as e:
                logger.warning("Error hasheando %s: %s", file_path, e)
                results[file_path] = None

            completed += 1
            if callback and completed % 10 == 0:
                callback(completed, total)

    return results


def _partial_hash(path: str) -> Optional[str]:
    """Compute partial hash for duplicate detection with Docker path support"""
    try:
        # Translate path if running in Docker mode
        resolved_path = _resolve_path_for_docker_hasher(path)
        with open(resolved_path, "rb") as f:
            return hashlib.md5(f.read(_PARTIAL_SIZE)).hexdigest()
    except (OSError, IOError):
        return None


def _full_hash(path: str) -> Optional[str]:
    """Compute full hash for duplicate detection with Docker path support"""
    try:
        # Translate path if running in Docker mode
        resolved_path = _resolve_path_for_docker_hasher(path)
        hasher = hashlib.sha256()
        with open(resolved_path, "rb") as f:
            while chunk := f.read(_CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None


def _resolve_path_for_docker_hasher(path: str) -> str:
    """Translate paths for file access in hasher module"""
    host_root = os.getenv("HOST_ROOT")
    if not host_root:
        return path
    
    # If path starts with /host/, it's already in Docker format
    if path.startswith("/host/"):
        return path
    
    # Translate native path to Docker format
    if platform.system() == "Windows":
        # C:\Users\X -> /host/c/Users/X
        if len(path) >= 2 and path[1] == ':':
            drive = path[0].lower()
            rest_path = path[2:].replace('\\', '/')
            return f"{host_root}/{drive}{rest_path}"
    else:
        # Linux/macOS: /home/x -> /host/home/x
        if path.startswith('/'):
            return f"{host_root}{path}"
    
    return path


def _build_group(hash_value: str, files: list[FileInfo]) -> DuplicateGroup:
    sorted_files = sorted(files, key=lambda f: f.created)
    original     = sorted_files[0]
    duplicates   = sorted_files[1:]
    total_size   = sum(f.size for f in files)
    wasted_size  = total_size - original.size

    return DuplicateGroup(
        hash        = hash_value,
        file_count  = len(files),
        total_size  = total_size,
        wasted_size = wasted_size,
        original    = original,
        duplicates  = duplicates,
    )