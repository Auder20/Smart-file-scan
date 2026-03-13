from __future__ import annotations

import os
import logging

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


def _is_path_from_registered_scan(path: str) -> bool:
    """FIX: Verifica si una ruta pertenece a algún scan registrado en SQLite"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM scan_files 
                WHERE path = ?
            """, (path,))
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
        if not os.path.isfile(path):
            failed.append(path)
            continue

        # FIX: Validar que la ruta pertenezca a algún scan registrado
        if not _is_path_from_registered_scan(path):
            logger.warning(f"Ruta no pertenece a ningún scan registrado: {path}")
            failed.append(path)
            continue

        try:
            size = os.path.getsize(path)

            if request.use_recycle:
                import send2trash
                send2trash.send2trash(path)
            else:
                os.remove(path)

            deleted.append(path)
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