from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.stats import compute_stats, StatsResult as StatsInternal
from app.core.scan_store import scan_store  # ARCH 2: Import centralized scan store

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
    # ARCH 2: Use scan_store instead of importing from routes_scanner
    result = scan_store.get_scan_result(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    stats = compute_stats(scan_id, result.files)

    # Convertir categorías al formato esperado por el frontend
    by_category_dict = []
    for cat in stats.by_category:
        by_category_dict.append({
            "category": cat.category.value,
            "file_count": cat.file_count,
            "total_size": cat.total_size,
            "percentage": cat.percentage
        })

    return StatsResponse(
        scan_id         = scan_id,
        total_files     = stats.total_files,
        total_size      = stats.total_size,
        by_category     = by_category_dict,
        empty_files     = stats.empty_files,
        old_files_count = stats.old_files_count,
        old_files_size  = stats.old_files_size,
    )