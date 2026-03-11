from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.stats import compute_stats, StatsResult as StatsInternal
from app.api.routes_scanner import _scan_results

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
    by_category:     list[CategoryStatsResponse]
    empty_files:     int
    old_files_count: int
    old_files_size:  int


@router.get("/{scan_id}")
def get_stats(scan_id: str) -> StatsResponse:
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    stats = compute_stats(scan_id, result.files)

    return StatsResponse(
        scan_id         = scan_id,
        total_files     = stats.total_files,
        total_size      = stats.total_size,
        by_category     = [
            CategoryStatsResponse(
                category   = c.category.value,
                file_count = c.file_count,
                total_size = c.total_size,
                percentage = c.percentage,
            )
            for c in stats.by_category
        ],
        empty_files     = stats.empty_files,
        old_files_count = stats.old_files_count,
        old_files_size  = stats.old_files_size,
    )