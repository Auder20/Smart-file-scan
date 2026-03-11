from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from app.models.file_info import FileCategory, FileInfo


class CategoryStats:
    def __init__(self, category: FileCategory, file_count: int, 
                 total_size: int, percentage: float):
        self.category   = category
        self.file_count = file_count
        self.total_size = total_size
        self.percentage = percentage


class StatsResult:
    def __init__(self, scan_id: str, total_files: int, total_size: int,
                 by_category: list, largest_files: list,
                 empty_files: int, old_files_count: int, old_files_size: int):
        self.scan_id         = scan_id
        self.total_files     = total_files
        self.total_size      = total_size
        self.by_category     = by_category
        self.largest_files   = largest_files
        self.empty_files     = empty_files
        self.old_files_count = old_files_count
        self.old_files_size  = old_files_size


def compute_stats(scan_id: str, files: list[FileInfo]) -> StatsResult:
    if not files:
        return StatsResult(scan_id, 0, 0, [], [], 0, 0, 0)

    total_size = sum(f.size for f in files)

    # ── Por categoría ─────────────────────────────────────────────────────
    count_map: dict[FileCategory, int] = defaultdict(int)
    size_map:  dict[FileCategory, int] = defaultdict(int)

    for f in files:
        count_map[f.category] += 1
        size_map[f.category]  += f.size

    by_category = []
    for category in FileCategory:
        if count_map[category] == 0:
            continue
        cat_size   = size_map[category]
        percentage = round(100 * cat_size / total_size, 2) if total_size > 0 else 0.0
        by_category.append(CategoryStats(category, count_map[category], cat_size, percentage))

    by_category.sort(key=lambda s: s.total_size, reverse=True)

    # ── Top 10 más grandes ────────────────────────────────────────────────
    largest_files = sorted(files, key=lambda f: f.size, reverse=True)[:10]

    # ── Archivos vacíos ───────────────────────────────────────────────────
    empty_files = sum(1 for f in files if f.size == 0)

    # ── Archivos viejos (sin modificar en más de 1 año) ───────────────────
    one_year_ago = datetime.now() - timedelta(days=365)
    old_files    = [f for f in files if f.modified < one_year_ago]

    return StatsResult(
        scan_id         = scan_id,
        total_files     = len(files),
        total_size      = total_size,
        by_category     = by_category,
        largest_files   = largest_files,
        empty_files     = empty_files,
        old_files_count = len(old_files),
        old_files_size  = sum(f.size for f in old_files),
    )