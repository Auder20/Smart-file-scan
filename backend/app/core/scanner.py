from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from collections.abc import Generator
from typing import Optional

from app.models.file_info import FileInfo, ScanRequest, ScanStatus
from app.core.classifier import classify_file
# FIX: importar normalize_scan_path para resolver rutas Docker antes de escanear
from app.core.path_utils import normalize_scan_path

logger = logging.getLogger(__name__)


def scan_directory(request: ScanRequest) -> Generator:
    """
    Genera FileInfo objects para cada archivo encontrado bajo request.path.

    FIX: el error "No such file or directory: '/mnt/host/d/estos'" ocurría
    porque scanner.py llamaba os.path.abspath(request.path) directamente.
    En modo Docker el frontend envía rutas nativas (D:\\...) que no existen
    en el contenedor; hay que traducirlas a /host/d/... primero.

    normalize_scan_path() hace exactamente eso:
      - D:\\Usuarios  →  /host/d/Usuarios  (Docker + Windows host)
      - /home/user    →  /host/home/user   (Docker + Linux host)
      - /host/d/...   →  /host/d/...       (ya en formato Docker, sin cambio)
      - cualquier     →  sin cambio        (modo nativo sin HOST_ROOT)
    """
    # Resolver la ruta antes de cualquier operación de sistema de archivos
    resolved_path = normalize_scan_path(request.path)
    root    = os.path.abspath(resolved_path)
    exclude = set(d.lower() for d in request.exclude_dirs)
    count   = 0
    max_files   = 0         # Sin límite de archivos
    start_time  = time.time()
    timeout     = 0         # Sin timeout

    if not os.path.isdir(root):
        logger.error(f"Directorio no encontrado: {root} (ruta original: {request.path})")
        yield {"type": "error", "message": f"Directorio no encontrado: {request.path}", "count": 0}
        return

    logger.info(f"Iniciando escaneo: {root} (resuelto desde: {request.path})")

    # Pila iterativa para evitar RecursionError en estructuras muy profundas
    stack: list[tuple[str, int]] = [(root, 0)]
    dir_count = 0
    files_since_last_yield = 0

    while stack:
        # Verificar timeout solo si está habilitado (timeout > 0)
        if timeout > 0 and time.time() - start_time > timeout:
            logger.warning(f"Escaneo detenido por timeout en {request.path}")
            yield {"type": "timeout", "count": count, "message": "Tiempo límite excedido"}
            return

        current_dir, depth = stack.pop()
        dir_count += 1

        if depth > request.max_depth:
            continue

        # Verificar límite de archivos solo si está habilitado (max_files > 0)
        if max_files > 0 and count >= max_files:
            logger.warning(f"Límite de {max_files:,} archivos alcanzado")
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
                            files_since_last_yield += 1
                            yield file_info
                            if files_since_last_yield >= 50:
                                yield {
                                    "type":        "progress",
                                    "count":       count,
                                    "current_dir": current_dir,
                                }
                                files_since_last_yield = 0
                    elif is_dir:
                        subdirs.append((entry.path, depth + 1))

                stack.extend(reversed(subdirs))
                
                # Report directory progress if we haven't yielded files recently
                if dir_count % 10 == 0:
                    yield {
                        "type":        "progress",
                        "count":       count,
                        "current_dir": current_dir,
                    }

        except PermissionError:
            logger.warning(f"Sin permisos: {current_dir}")
        except OSError as e:
            logger.error(f"Error escaneando {current_dir}: {e}")

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
        logger.error(f"Error procesando {entry.path}: {e}")
        return None