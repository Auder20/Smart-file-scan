from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.stats import compute_stats
from app.core.scan_store import scan_store

router = APIRouter(prefix="/api/stats", tags=["stats"])


class CategoryStatsResponse(BaseModel):
    category:   str
    file_count: int
    total_size: int
    percentage: float


class StatsResponse(BaseModel):
    scan_id:         str
    total_files:     int
    total_size:      int
    by_category:     list[dict]
    empty_files:     int
    old_files_count: int
    old_files_size:  int


@router.get("/{scan_id}")
def get_stats(scan_id: str) -> StatsResponse:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    # Si los archivos están en memoria, calcular directamente
    if result.files and not result.files_truncated:
        stats = compute_stats(scan_id, result.files)
        by_category_dict = [
            {"category": c.category.value, "file_count": c.file_count,
             "total_size": c.total_size, "percentage": c.percentage}
            for c in stats.by_category
        ]
        return StatsResponse(
            scan_id=scan_id, total_files=stats.total_files,
            total_size=stats.total_size, by_category=by_category_dict,
            empty_files=stats.empty_files, old_files_count=stats.old_files_count,
            old_files_size=stats.old_files_size,
        )

    # Caso post-reinicio o scan truncado: calcular desde SQLite directamente
    from app.db.database import get_db_cursor
    from datetime import datetime, timedelta

    try:
        with get_db_cursor() as cursor:
            # Total y tamaño
            cursor.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size),0) as total "
                "FROM scan_files WHERE scan_id=?", (scan_id,))
            row = cursor.fetchone()
            total_files = row["cnt"]
            total_size  = row["total"]

            # Por categoría
            cursor.execute("""
                SELECT category,
                       COUNT(*) as file_count,
                       COALESCE(SUM(size),0) as total_size
                FROM scan_files WHERE scan_id=?
                GROUP BY category ORDER BY total_size DESC
            """, (scan_id,))
            cats = cursor.fetchall()
            by_category_dict = []
            for c in cats:
                pct = round(c["total_size"] * 100.0 / total_size, 2) if total_size > 0 else 0.0
                by_category_dict.append({
                    "category":   c["category"] or "other",
                    "file_count": c["file_count"],
                    "total_size": c["total_size"],
                    "percentage": pct,
                })

            # Archivos vacíos
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM scan_files WHERE scan_id=? AND size=0",
                (scan_id,))
            empty_files = cursor.fetchone()["cnt"]

            # Archivos "viejos" (más de 2 años)
            cutoff = (datetime.now() - timedelta(days=730)).isoformat()
            cursor.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size),0) as sz "
                "FROM scan_files WHERE scan_id=? AND modified < ?",
                (scan_id, cutoff))
            old_row = cursor.fetchone()
            old_files_count = old_row["cnt"]
            old_files_size  = old_row["sz"]

    except Exception as e:
        raise HTTPException(500, detail=f"Error calculando estadísticas: {e}")

    return StatsResponse(
        scan_id=scan_id, total_files=total_files, total_size=total_size,
        by_category=by_category_dict, empty_files=empty_files,
        old_files_count=old_files_count, old_files_size=old_files_size,
    )