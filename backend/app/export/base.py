"""
Base exporter class for all export formats.
"""

from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator, Dict, Any

from app.db.database import get_scan, get_db_cursor

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """Base class for all exporters with common functionality."""
    
    def __init__(self, scan_id: str):
        self.scan_id = scan_id
        self.meta = self._get_meta()
    
    def _get_meta(self) -> dict:
        """Get scan metadata from SQLite or memory."""
        scan_meta = get_scan(self.scan_id)
        if scan_meta:
            return {
                "scan_id": self.scan_id,
                "root_path": scan_meta.get("root_path", ""),
                "total_files": scan_meta.get("total_files", 0),
                "total_size": scan_meta.get("total_size", 0),
                "duration_sec": scan_meta.get("duration_sec", 0),
                "scanned_at": str(scan_meta.get("scanned_at", datetime.now().isoformat())),
            }
        
        # Fallback to scan_store if not in database
        from app.core.scan_store import scan_store
        result = scan_store.get_scan_result(self.scan_id)
        if result:
            return {
                "scan_id": self.scan_id,
                "root_path": result.root_path,
                "total_files": result.total_files,
                "total_size": result.total_size,
                "duration_sec": result.duration_sec,
                "scanned_at": result.scanned_at.isoformat(),
            }
        
        raise ValueError(f"Scan '{self.scan_id}' not found")
    
    def _iter_files(self) -> Generator[Dict[str, Any], None, None]:
        """Iterate over all files in the scan, yielding file data dictionaries."""
        offset = 0
        batch_size = 2000
        
        while True:
            try:
                with get_db_cursor() as cursor:
                    cursor.execute(
                        "SELECT name, path, size, extension, category, modified "
                        "FROM scan_files WHERE scan_id=? ORDER BY path LIMIT ? OFFSET ?",
                        (self.scan_id, batch_size, offset)
                    )
                    rows = cursor.fetchall()
            except Exception as e:
                logger.error(f"Error reading files for scan {self.scan_id}: {e}")
                raise RuntimeError(f"Error reading files: {e}")
            
            if not rows:
                break
                
            for row in rows:
                yield {
                    "name": row["name"] or "",
                    "path": row["path"] or "",
                    "size": row["size"] or 0,
                    "extension": row["extension"] or "",
                    "category": row["category"] or "other",
                    "modified": str(row["modified"] or "")[:19],
                }
            
            offset += batch_size
            if len(rows) < batch_size:
                break
    
    def _get_categories(self) -> list[dict]:
        """Get category statistics for the scan."""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT category, COUNT(*) as c, COALESCE(SUM(size),0) as s
                FROM scan_files WHERE scan_id=? GROUP BY category ORDER BY s DESC
            """, (self.scan_id,))
            
            total_size = self.meta["total_size"]
            return [
                {
                    "category": row["category"] or "other",
                    "file_count": row["c"],
                    "total_size": row["s"],
                    "percentage": round(row["s"] * 100.0 / total_size, 1) if total_size > 0 else 0
                }
                for row in cursor.fetchall()
            ]
    
    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    @abstractmethod
    def export(self) -> tuple[bytes, str, str]:
        """
        Export the scan data.
        
        Returns:
            Tuple of (content_bytes, media_type, filename)
        """
        pass
    
    def _generate_filename(self, extension: str) -> str:
        """Generate a filename with timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"scan_{self.scan_id}_{timestamp}.{extension}"
