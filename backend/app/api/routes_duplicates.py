from __future__ import annotations

import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.file_info import DuplicateGroup
from app.core.hasher import find_duplicates
from app.api.routes_scanner import _scan_results

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
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    groups = find_duplicates(result.files)
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


@router.delete("/files")
def delete_files(request: DeleteRequest) -> DeleteResult:
    deleted     = []
    failed      = []
    space_freed = 0

    for path in request.paths:
        if not os.path.isfile(path):
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