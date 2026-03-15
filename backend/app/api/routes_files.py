from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.file_info import FileInfo, FileCategory
from app.core.scan_store import scan_store
from app.db.database import get_files_paginated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


class FileInfoResponse(BaseModel):
    path:      str
    name:      str
    size:      int
    extension: str
    category:  str
    modified:  str
    created:   str
    hash:      Optional[str] = None


class FilesListResponse(BaseModel):
    files:       list[FileInfoResponse]
    total_count: int
    page:        int
    page_size:   int
    total_pages: int
    has_more:    bool


def _to_response(f: FileInfo) -> FileInfoResponse:
    return FileInfoResponse(
        path=f.path, name=f.name, size=f.size,
        extension=f.extension,
        category=f.category.value if hasattr(f.category, "value") else str(f.category),
        modified=f.modified.isoformat(),
        created=f.created.isoformat(),
        hash=f.hash,
    )


@router.get("/{scan_id}")
def list_files(
    scan_id:   str,
    page:      int           = Query(default=1,   ge=1),
    page_size: int           = Query(default=50,  ge=1, le=1000),
    search:    Optional[str] = Query(default=None),
    category:  Optional[str] = Query(default=None),
    min_size:  Optional[int] = Query(default=None),
    max_size:  Optional[int] = Query(default=None),
) -> FilesListResponse:
    """
    Lista archivos con paginación y filtros.

    FIX: cuando el escaneo tiene files_truncated=True la versión anterior
    filtraba sobre los primeros 1000 archivos en memoria, devolviendo
    resultados incompletos. Ahora delega siempre a SQLite con filtros
    nativos, garantizando resultados sobre el dataset completo.
    """
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    # ── Ruta rápida: todo en memoria (escaneos pequeños ≤ 1000 archivos) ──────
    if not result.files_truncated:
        files = result.files[:]

        if search:
            sl = search.lower()
            files = [f for f in files if sl in f.name.lower() or sl in f.path.lower()]
        if category:
            files = [f for f in files if f.category.value == category]
        if min_size is not None:
            files = [f for f in files if f.size >= min_size]
        if max_size is not None:
            files = [f for f in files if f.size <= max_size]

        files.sort(key=lambda f: f.size, reverse=True)
        total = len(files)
        start = (page - 1) * page_size
        page_files = files[start: start + page_size]
        total_pages = max(1, (total + page_size - 1) // page_size)

        return FilesListResponse(
            files=[_to_response(f) for f in page_files],
            total_count=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more=(start + page_size) < total,
        )

    # ── Ruta SQLite: escaneos grandes, filtros nativos ─────────────────────────
    db_filters: dict = {}
    if category:
        db_filters["category"] = category
    if min_size is not None:
        db_filters["min_size"] = min_size
    if max_size is not None:
        db_filters["max_size"] = max_size
    # Nota: el filtro `search` se aplica post-query (SQLite LIKE es lento sin FTS)
    # Para datasets muy grandes se puede agregar FTS5 en el futuro.

    paginated = get_files_paginated(scan_id, page, page_size, db_filters or None)
    files_page = paginated["files"]

    if search:
        sl = search.lower()
        files_page = [f for f in files_page if sl in f.name.lower() or sl in f.path.lower()]

    total      = paginated["total_files"]
    total_pages = paginated["total_pages"]

    return FilesListResponse(
        files=[_to_response(f) for f in files_page],
        total_count=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_more=page < total_pages,
    )


@router.get("/{scan_id}/largest")
def get_largest_files(
    scan_id: str,
    limit:   int = Query(default=10, ge=1, le=100),
) -> list[FileInfoResponse]:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    if not result.files_truncated:
        largest = sorted(result.files, key=lambda f: f.size, reverse=True)[:limit]
        return [_to_response(f) for f in largest]

    # Para escaneos truncados, consultar SQLite ordenando por size DESC
    from app.db.database import get_db_cursor
    from app.models.file_info import FileInfo, FileCategory
    from datetime import datetime

    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM scan_files WHERE scan_id = ? ORDER BY size DESC LIMIT ?",
                (scan_id, limit),
            )
            rows = cursor.fetchall()
            files = []
            for row in rows:
                fi = FileInfo(
                    path=row["path"], name=row["name"], size=row["size"],
                    extension=row["extension"] or "",
                    category=FileCategory(row["category"]) if row["category"] else FileCategory.OTHER,
                    modified=datetime.fromisoformat(row["modified"]) if row["modified"] else datetime.now(),
                    created=datetime.fromisoformat(row["created"])  if row["created"]  else datetime.now(),
                )
                if row["hash"]:
                    fi.hash = row["hash"]
                files.append(fi)
        return [_to_response(f) for f in files]
    except Exception as e:
        logger.error(f"Error fetching largest files from SQLite: {e}")
        raise HTTPException(500, detail="Error obteniendo archivos más grandes")


@router.get("/{scan_id}/extensions")
def get_extension_stats(scan_id: str) -> list[dict]:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    if not result.files_truncated:
        return _compute_extension_stats(result.files)

    # Para escaneos truncados, agregar directamente en SQLite (mucho más eficiente)
    from app.db.database import get_db_cursor
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT
                    UPPER(COALESCE(NULLIF(extension,''), 'SIN EXTENSIÓN')) AS ext,
                    COUNT(*) AS cnt,
                    SUM(size) AS total_size,
                    SUM(size) * 100.0 / NULLIF(SUM(SUM(size)) OVER (), 0) AS pct
                FROM scan_files
                WHERE scan_id = ?
                GROUP BY ext
                ORDER BY total_size DESC
            """, (scan_id,))
            return [
                {"extension": r["ext"], "count": r["cnt"],
                 "total_size": r["total_size"], "percentage": round(r["pct"] or 0, 2)}
                for r in cursor.fetchall()
            ]
    except Exception as e:
        logger.error(f"Error computing extension stats from SQLite: {e}")
        raise HTTPException(500, detail="Error calculando estadísticas de extensiones")


@router.get("/{scan_id}/categories")
def get_category_stats(scan_id: str) -> list[dict]:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    if not result.files_truncated:
        return _compute_category_stats(result.files)

    from app.db.database import get_db_cursor
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT
                    category,
                    COUNT(*) AS cnt,
                    SUM(size) AS total_size,
                    SUM(size) * 100.0 / NULLIF(SUM(SUM(size)) OVER (), 0) AS pct
                FROM scan_files
                WHERE scan_id = ?
                GROUP BY category
                ORDER BY total_size DESC
            """, (scan_id,))
            return [
                {"category": r["category"] or "other", "count": r["cnt"],
                 "total_size": r["total_size"], "percentage": round(r["pct"] or 0, 2)}
                for r in cursor.fetchall()
            ]
    except Exception as e:
        logger.error(f"Error computing category stats from SQLite: {e}")
        raise HTTPException(500, detail="Error calculando estadísticas por categoría")


# ── Helpers en memoria ─────────────────────────────────────────────────────────

def _compute_extension_stats(files: list[FileInfo]) -> list[dict]:
    stats: dict = {}
    total_size = sum(f.size for f in files)
    for f in files:
        ext = (f.extension.upper() if f.extension else "SIN EXTENSIÓN")
        if ext not in stats:
            stats[ext] = {"extension": ext, "count": 0, "total_size": 0, "percentage": 0.0}
        stats[ext]["count"] += 1
        stats[ext]["total_size"] += f.size
    for s in stats.values():
        s["percentage"] = round(100 * s["total_size"] / total_size, 2) if total_size else 0.0
    return sorted(stats.values(), key=lambda x: x["total_size"], reverse=True)


def _compute_category_stats(files: list[FileInfo]) -> list[dict]:
    stats: dict = {}
    total_size = sum(f.size for f in files)
    for f in files:
        cat = f.category.value
        if cat not in stats:
            stats[cat] = {"category": cat, "count": 0, "total_size": 0, "percentage": 0.0}
        stats[cat]["count"] += 1
        stats[cat]["total_size"] += f.size
    for s in stats.values():
        s["percentage"] = round(100 * s["total_size"] / total_size, 2) if total_size else 0.0
    return sorted(stats.values(), key=lambda x: x["total_size"], reverse=True)