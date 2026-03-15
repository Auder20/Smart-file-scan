from __future__ import annotations

import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.file_info import DuplicateGroup
from app.core.hasher import find_duplicates
from app.core.scan_store import scan_store
from app.db.database import get_files_paginated, get_db_cursor
from app.core.path_utils import resolve_path_for_docker
# PRIORIDAD 5: importar validadores de seguridad centralizados
from app.core.security import validate_delete_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])

# PRIORIDAD 5: límite máximo de paths por petición de borrado
MAX_DELETE_PATHS = 500


class DuplicatesResult(BaseModel):
    scan_id:          str
    groups:           list[dict]
    total_groups:     int
    total_duplicates: int
    total_wasted:     int
    analyzed_files:   int


class DeleteRequest(BaseModel):
    # PRIORIDAD 5: max_length limita el payload a MAX_DELETE_PATHS rutas
    paths:       list[str] = Field(..., min_length=1, max_length=MAX_DELETE_PATHS)
    use_recycle: bool      = True


class DeleteResult(BaseModel):
    deleted_count: int
    space_freed:   int
    deleted:       list[str]
    failed:        list[str]


# ── Duplicates ────────────────────────────────────────────────────────────────

@router.get("/{scan_id}")
def get_duplicates(scan_id: str) -> DuplicatesResult:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    files = result.files
    if result.files_truncated:
        logger.info(f"Loading all files from SQLite for scan {scan_id}")
        all_files = []
        page = 1
        while True:
            paginated = get_files_paginated(scan_id, page, page_size=1000)
            all_files.extend(paginated["files"])
            if page >= paginated["total_pages"]:
                break
            page += 1
        files = all_files

    groups = find_duplicates(files)
    total_wasted     = sum(g.wasted_size for g in groups)
    total_duplicates = sum(len(g.duplicates) for g in groups)

    groups_dict = []
    for g in groups:
        gd: dict = {
            "hash": g.hash, "file_count": g.file_count,
            "total_size": g.total_size, "wasted_size": g.wasted_size,
            "duplicates": [],
        }
        gd["duplicates"].append({
            "path": g.original.path, "name": g.original.name,
            "size": g.original.size, "modified": g.original.modified.isoformat(),
            "is_original": True,
        })
        for dup in g.duplicates:
            gd["duplicates"].append({
                "path": dup.path, "name": dup.name, "size": dup.size,
                "modified": dup.modified.isoformat(), "is_original": False,
            })
        groups_dict.append(gd)

    return DuplicatesResult(
        scan_id=scan_id, groups=groups_dict,
        total_groups=len(groups), total_duplicates=total_duplicates,
        total_wasted=total_wasted, analyzed_files=result.total_files,
    )


# ── Helpers privados ──────────────────────────────────────────────────────────

def _is_path_from_registered_scan(path: str) -> bool:
    """Verifica que la ruta pertenezca a algún scan registrado en SQLite."""
    try:
        resolved  = resolve_path_for_docker(path)
        alt_paths = list({path, resolved})

        if resolved.startswith("/host/"):
            relative = resolved[len("/host/"):]
            if len(relative) >= 2 and relative[1] == "/":
                drive = relative[0].upper()
                rest  = relative[2:].replace("/", "\\")
                alt_paths.append(f"{drive}:\\{rest}")

        with get_db_cursor() as cursor:
            ph = ",".join("?" for _ in alt_paths)
            cursor.execute(f"SELECT COUNT(*) FROM scan_files WHERE path IN ({ph})", alt_paths)
            return cursor.fetchone()[0] > 0
    except Exception as e:
        logger.error(f"Error verificando ruta {path}: {e}")
        return False


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/files")
def delete_files(request: DeleteRequest) -> DeleteResult:
    """
    PRIORIDAD 5 — Mejoras de seguridad aplicadas:
      1. validate_delete_path() detecta path traversal (../, %2e%2e, etc.)
         y rutas de sistema antes de cualquier operación de I/O.
      2. MAX_DELETE_PATHS = 500 limita el tamaño del payload para prevenir
         eliminaciones masivas accidentales o maliciosas.
      3. _is_path_from_registered_scan() garantiza que solo se borren archivos
         que el usuario escaneó explícitamente.
    """
    deleted:     list[str] = []
    failed:      list[str] = []
    space_freed: int       = 0

    for raw_path in request.paths:

        # 1. Validación de seguridad (traversal + sistema)
        try:
            safe_path = validate_delete_path(raw_path)
        except ValueError as e:
            logger.warning(f"Ruta rechazada por seguridad: {e}")
            failed.append(raw_path)
            continue

        # 2. Resolver para Docker
        resolved   = resolve_path_for_docker(safe_path)
        candidates = list({resolved, safe_path})
        if resolved.startswith("/host/"):
            relative = resolved[len("/host/"):]
            if len(relative) >= 2 and relative[1] == "/":
                drive = relative[0].upper()
                rest  = relative[2:].replace("/", "\\")
                candidates.append(f"{drive}:\\{rest}")

        actual_path = next((p for p in candidates if os.path.isfile(p)), None)
        if actual_path is None:
            logger.warning(f"Archivo no encontrado: {raw_path}")
            failed.append(raw_path)
            continue

        # 3. El archivo debe pertenecer a un scan registrado
        if not _is_path_from_registered_scan(raw_path):
            logger.warning(f"Ruta no registrada en ningún scan: {raw_path}")
            failed.append(raw_path)
            continue

        # 4. Borrado
        try:
            size = os.path.getsize(actual_path)
            if request.use_recycle:
                import send2trash
                send2trash.send2trash(actual_path)
            else:
                os.remove(actual_path)
            deleted.append(raw_path)
            space_freed += size
        except Exception as e:
            logger.error(f"No se pudo eliminar {raw_path}: {e}")
            failed.append(raw_path)

    return DeleteResult(
        deleted_count=len(deleted),
        space_freed=space_freed,
        deleted=deleted,
        failed=failed,
    )