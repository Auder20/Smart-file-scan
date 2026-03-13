from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from collections.abc import Generator
from typing import Optional
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib
import asyncio
import websockets

from app.models.file_info import FileInfo, ScanRequest, ScanStatus
from app.core.classifier import classify_file

logger = logging.getLogger(__name__)

def _estimate_file_count(path: str) -> int:
    """Estimar cantidad de archivos para decidir si usar paralelismo"""
    count = 0
    try:
        for root, dirs, files in os.walk(path):
            depth = root.replace(path, "").count(os.sep)
            if depth >= 2:
                dirs[:] = []
                continue
            count += len(files)
            if count > 100_000:
                return count
    except Exception:
        pass
    return count


async def send_progress(websocket, progress):
    await websocket.send(json.dumps(progress))


def scan_directory_parallel(request: ScanRequest) -> Generator:
    """Escaneo paralelo para alto rendimiento en discos grandes"""
    root = os.path.abspath(request.path)
    exclude = set(d.lower() for d in request.exclude_dirs)
    
    # Recolectar directorios principales primero
    main_dirs = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() not in exclude:
                        if not request.include_hidden and entry.name.startswith("."):
                            continue
                        main_dirs.append(entry.path)
    except (OSError, PermissionError) as e:
        logger.error(f"Error escaneando {root}: {e}")
        return
    
    # Configurar workers basados en CPU cores
    max_workers = min(multiprocessing.cpu_count(), 8)  # Máximo 8 workers
    logger.info(f"Iniciando escaneo paralelo con {max_workers} workers para {len(main_dirs)} directorios")
    
    # Procesar directorios en paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Crear futures para cada directorio
        future_to_dir = {
            executor.submit(_scan_single_directory, dir_path, request, exclude): dir_path 
            for dir_path in main_dirs[:max_workers]  # Limitar workers iniciales
        }
        
        processed_dirs = set()
        total_count = 0
        
        while future_to_dir:
            # Esperar por cualquier futuro que termine
            completed_futures = []
            for future in future_to_dir:
                if future.done():
                    completed_futures.append(future)
            
            if not completed_futures:
                time.sleep(0.1)  # Pequeña pausa para no sobrecargar CPU
                continue
            
            # Procesar directorios completados
            for future in completed_futures:
                dir_path = future_to_dir[future]
                if dir_path not in processed_dirs:
                    try:
                        count, files = future.result()  
                        total_count += count
                        processed_dirs.add(dir_path)
                        
                        # Hacer yield de cada FileInfo encontrado
                        for file_info in files:
                            yield file_info
                        
                        # Encontrar más directorios para procesar
                        if len(processed_dirs) < len(main_dirs):
                            remaining_dirs = [d for d in main_dirs if d not in processed_dirs]
                            if remaining_dirs:
                                new_dir = remaining_dirs[0]
                                future_to_dir[executor.submit(_scan_single_directory, new_dir, request, exclude)] = new_dir
                        
                        yield {
                            "type": "progress",
                            "count": total_count,
                            "current_dir": dir_path,
                            "parallel_workers": len([f for f in future_to_dir.values() if not f.done()])
                        }
                        
                    except Exception as e:
                        logger.error(f"Error procesando {dir_path}: {e}")
                    
                    # Remover futuro procesado
                    del future_to_dir[future]
        
        yield {"type": "done", "count": total_count}


def _scan_single_directory(dir_path: str, request: ScanRequest, exclude: set) -> tuple[int, list[FileInfo]]:
    """Escanea un solo directorio (usado por workers paralelos)"""
    count = 0
    files = []
    max_depth = request.max_depth
    stack: list[tuple[str, int]] = [(dir_path, 0)]
    
    while stack:
        current_dir, depth = stack.pop()
        
        if depth > max_depth:
            continue
        
        try:
            with os.scandir(current_dir) as entries:
                subdirs = []
                
                for entry in entries:
                    if entry.name.lower() in exclude:
                        continue
                    if not request.include_hidden and entry.name.startswith("."):
                        continue
                    
                    try:
                        is_file = entry.is_file(follow_symlinks=False)
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    
                    if is_file:
                        file_info = _build_file_info(entry)
                        if file_info is not None:
                            count += 1
                            files.append(file_info)  # FIX: Acumular archivos para yield después
                    elif is_dir:
                        subdirs.append((entry.path, depth + 1))
                
                stack.extend(reversed(subdirs))
        except (PermissionError, OSError) as e:
            logger.debug(f"Error en {current_dir}: {e}")
    
    return count, files


def scan_directory(request: ScanRequest) -> Generator:
    root    = os.path.abspath(request.path)
    exclude = set(d.lower() for d in request.exclude_dirs)
    count   = 0
    max_files = 100000  # Límite aumentado para evitar congelamiento
    start_time = time.time()
    timeout = 300     # 5 minutos máximo por escaneo

    # Usamos una pila en vez de recursión para evitar
    # RecursionError en directorios muy profundos.
    # Cada elemento es (directorio, profundidad_actual)
    stack: list[tuple[str, int]] = [(root, 0)]

    while stack:
        # Verificar timeout
        if time.time() - start_time > timeout:
            logger.warning(f"Escaneo detenido por timeout en {request.path}")
            yield {"type": "timeout", "count": count}
            return

        current_dir, depth = stack.pop()

        if depth > request.max_depth:
            continue

        if count >= max_files:
            logger.warning(f"Límite de archivos alcanzado en {request.path}")
            yield {"type": "limit", "count": count}
            return

        try:
            with os.scandir(current_dir) as entries:
                subdirs = []

                for entry in entries:
                    if entry.name.lower() in exclude:
                        continue
                    if not request.include_hidden and entry.name.startswith("."):
                        continue

                    try:
                        is_file = entry.is_file(follow_symlinks=False)
                        is_dir  = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue

                    if is_file:
                        file_info = _build_file_info(entry)
                        if file_info is not None:
                            count += 1
                            yield file_info

                            if count % 50 == 0:
                                yield {
                                    "type":        "progress",
                                    "count":       count,
                                    "current_dir": current_dir,
                                }

                    elif is_dir:
                        subdirs.append((entry.path, depth + 1))

                stack.extend(reversed(subdirs))

        except PermissionError:
            logger.warning("Sin permisos: %s", current_dir)
        except OSError as e:
            logger.error("Error escaneando %s: %s", current_dir, e)

    yield {"type": "done", "count": count}


def _build_file_info(entry: os.DirEntry) -> Optional[FileInfo]:
    try:
        stat      = entry.stat(follow_symlinks=False)
        modified  = datetime.fromtimestamp(stat.st_mtime)
        created   = datetime.fromtimestamp(stat.st_ctime)
        _, ext    = os.path.splitext(entry.name)
        extension = ext.lstrip(".").lower() if ext else ""

        return FileInfo(
            path      = entry.path,
            name      = entry.name,
            size      = stat.st_size,
            extension = extension,
            category  = classify_file(extension),
            modified  = modified,
            created   = created,
        )
    except (OSError, ValueError) as e:
        logger.error("Error procesando %s: %s", entry.path, e)
        return None