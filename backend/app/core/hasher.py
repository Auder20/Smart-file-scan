from __future__ import annotations

import hashlib
import os
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

from app.models.file_info import FileInfo, DuplicateGroup

logger = logging.getLogger(__name__)

_CHUNK_SIZE   = 8 * 1024   # 8KB por chunk al leer archivos grandes
_PARTIAL_SIZE = 4 * 1024   # 4KB para el hash de pre-filtrado


def find_duplicates(
    files: list[FileInfo],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[DuplicateGroup]:

    if len(files) < 2:
        return []

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
    partial_hashes = _compute_hashes_parallel(flat, partial=True)

    by_partial: dict[str, list[FileInfo]] = defaultdict(list)
    for file_info, ph in partial_hashes.items():
        if ph:
            by_partial[ph].append(file_info)

    candidates2 = [g for g in by_partial.values() if len(g) >= 2]

    if not candidates2:
        return []

    # ── Fase 3: hash completo SHA-256 ─────────────────────────────────────
    flat2 = [f for group in candidates2 for f in group]
    full_hashes = _compute_hashes_parallel(flat2, partial=False, callback=progress_callback)

    for file_info, fh in full_hashes.items():
        file_info.hash = fh

    by_full: dict[str, list[FileInfo]] = defaultdict(list)
    for file_info, fh in full_hashes.items():
        if fh:
            by_full[fh].append(file_info)

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
    max_workers: int = 4,
) -> dict[FileInfo, Optional[str]]:

    results: dict[FileInfo, Optional[str]] = {}
    completed = 0
    total     = len(files)
    hash_func = _partial_hash if partial else _full_hash

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(hash_func, f.path): f
            for f in files
        }

        for future in as_completed(future_to_file):
            file_info = future_to_file[future]
            try:
                results[file_info] = future.result()
            except Exception as e:
                logger.warning("Error hasheando %s: %s", file_info.path, e)
                results[file_info] = None

            completed += 1
            if callback and completed % 10 == 0:
                callback(completed, total)

    return results


def _partial_hash(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read(_PARTIAL_SIZE)).hexdigest()
    except (OSError, IOError):
        return None


def _full_hash(path: str) -> Optional[str]:
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(_CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None


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