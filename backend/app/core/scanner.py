from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from collections.abc import Generator
from typing import Optional

from app.models.file_info import FileInfo, ScanRequest, ScanStatus
from app.core.classifier import classify_file

logger = logging.getLogger(__name__)


def scan_directory(request: ScanRequest) -> Generator:
    root    = os.path.abspath(request.path)
    exclude = set(d.lower() for d in request.exclude_dirs)
    count   = 0

    # Usamos una pila en vez de recursión para evitar
    # RecursionError en directorios muy profundos.
    # Cada elemento es (directorio, profundidad_actual)
    stack: list[tuple[str, int]] = [(root, 0)]

    while stack:
        current_dir, depth = stack.pop()

        if depth > request.max_depth:
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
        logger.debug("No se pudo procesar %s: %s", entry.path, e)
        return None


def collect_all_files(request: ScanRequest) -> tuple[list[FileInfo], float]:
    files: list[FileInfo] = []
    start = time.time()

    for event in scan_directory(request):
        if isinstance(event, FileInfo):
            files.append(event)

    return files, round(time.time() - start, 2)