from __future__ import annotations

import os
import logging
import platform

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.file_info import DuplicateGroup
from app.core.hasher import find_duplicates
from app.core.scan_store import scan_store
from app.db.database import get_files_paginated, get_scan, get_db_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


class DuplicatesResult(BaseModel):
    scan_id:        str
    groups:         list[dict]
    total_groups:   int
    total_duplicates: int
    total_wasted:   int
    analyzed_files: int


class DeleteRequest(BaseModel):
    paths:       list[str] = Field(..., min_length=1)
    use_recycle: bool      = True


class DeleteResult(BaseModel):
    deleted_count: int
    space_freed:   int
    deleted:       list[str]
    failed:        list[str]


@router.get("/{scan_id}")
def get_duplicates(scan_id: str) -> DuplicatesResult:
    # ARCH 2: Use scan_store instead of importing from routes_scanner
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    # FIX: Usar SQLite si los archivos están truncados
    files = result.files
    if result.files_truncated:
        logger.info(f"Loading files from SQLite for truncated scan {scan_id}")
        # Cargar todos los archivos desde SQLite en lotes
        all_files = []
        page = 1
        while True:
            paginated_result = get_files_paginated(scan_id, page, page_size=1000)
            all_files.extend(paginated_result['files'])
            if page >= paginated_result['total_pages']:
                break
            page += 1
        files = all_files

    groups = find_duplicates(files)
    total_wasted = sum(g.wasted_size for g in groups)
    total_duplicates = sum(len(g.duplicates) for g in groups)

    # Convertir grupos a formato esperado por el frontend
    groups_dict = []
    for group in groups:
        group_dict = {
            "hash": group.hash,
            "file_count": group.file_count,
            "total_size": group.total_size,
            "wasted_size": group.wasted_size,
            "duplicates": []
        }
        
        # Agregar archivo original
        group_dict["duplicates"].append({
            "path": group.original.path,
            "name": group.original.name,
            "size": group.original.size,
            "modified": group.original.modified.isoformat(),
            "is_original": True
        })
        
        # Agregar archivos duplicados
        for dup in group.duplicates:
            group_dict["duplicates"].append({
                "path": dup.path,
                "name": dup.name,
                "size": dup.size,
                "modified": dup.modified.isoformat(),
                "is_original": False
            })
        
        groups_dict.append(group_dict)

    return DuplicatesResult(
        scan_id        = scan_id,
        groups         = groups_dict,
        total_groups   = len(groups),
        total_duplicates = total_duplicates,
        total_wasted   = total_wasted,
        analyzed_files = result.total_files,
    )


def _resolve_path_for_docker_api(path: str) -> str:
    """Translate paths between Docker and native format for validation"""
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


def _is_path_from_registered_scan(path: str) -> bool:
    """FIX: Verifica si una ruta pertenece a algún scan registrado en SQLite"""
    try:
        # First check if path needs Docker translation
        resolved_path = _resolve_path_for_docker_api(path)
        
        # Also generate alternative path formats for better matching
        alt_paths = [path, resolved_path]
        
        # Add reverse translation (from docker to native)
        if resolved_path.startswith("/host/"):
            relative = resolved_path[len("/host/"):]
            if len(relative) >= 2 and relative[1] == '/':
                drive_letter = relative[0].upper()
                rest = relative[2:].replace('/', '\\')
                native_path = f"{drive_letter}:\\{rest}"
                alt_paths.append(native_path)
        
        with get_db_cursor() as cursor:
            # Build dynamic query to check all possible path formats
            placeholders = ','.join(['?' for _ in alt_paths])
            cursor.execute(f"""
                SELECT COUNT(*) FROM scan_files 
                WHERE path IN ({placeholders})
            """, alt_paths)
            return cursor.fetchone()[0] > 0
    except Exception as e:
        logger.error(f"Error verificando ruta {path}: {e}")
        return False


@router.delete("/files")
def delete_files(request: DeleteRequest) -> DeleteResult:
    deleted     = []
    failed      = []
    space_freed = 0

    for path in request.paths:
        # FIX: Translate path from native format to Docker format if needed
        resolved_path = _resolve_path_for_docker_api(path)
        
        # Check if file exists using resolved path first, then try alternatives
        paths_to_try = [resolved_path, path]
        
        # Also try reverse translation
        if resolved_path.startswith("/host/"):
            relative = resolved_path[len("/host/"):]
            if len(relative) >= 2 and relative[1] == '/':
                drive_letter = relative[0].upper()
                rest = relative[2:].replace('/', '\\')
                native_path = f"{drive_letter}:\\{rest}"
                paths_to_try.append(native_path)
        
        actual_path = None
        for p in paths_to_try:
            if os.path.isfile(p):
                actual_path = p
                break
        
        if actual_path is None:
            logger.warning(f"File not found: {path} (tried: {paths_to_try})")
            failed.append(path)
            continue
        
        # FIX: Validar que la ruta pertenezca a algún scan registrado
        if not _is_path_from_registered_scan(path):
            logger.warning(f"Ruta no pertenece a ningún scan registrado: {path}")
            failed.append(path)
            continue

        try:
            size = os.path.getsize(actual_path)

            if request.use_recycle:
                import send2trash
                send2trash.send2trash(actual_path)
            else:
                os.remove(actual_path)

            deleted.append(path)  # Return original path in response
            space_freed += size

        except Exception as e:
            logger.error("No se pudo eliminar %s: %s", path, e)
            failed.append(path)

    return DeleteResult(
        deleted_count = len(deleted),
        space_freed   = space_freed,
        deleted       = deleted,
        failed        = failed,
    )