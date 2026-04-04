"""
JSON exporter for scan results.
"""

from __future__ import annotations

import json
from typing import Dict, Any, Tuple

from .base import BaseExporter


class JSONExporter(BaseExporter):
    """Export scan results to JSON format."""
    
    def export(self) -> Tuple[bytes, str, str]:
        """Export scan data to JSON format."""
        
        # Build the complete JSON structure
        export_data = {
            "metadata": {
                "scan_id": self.meta["scan_id"],
                "root_path": self.meta["root_path"],
                "scanned_at": self.meta["scanned_at"],
                "total_files": self.meta["total_files"],
                "total_size": self.meta["total_size"],
                "duration_sec": self.meta["duration_sec"],
                "exported_at": self.meta["scanned_at"]  # Using scan time as export time
            },
            "categories": self._get_categories(),
            "files": list(self._iter_files())
        }
        
        # Convert to JSON bytes
        json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8')
        filename = self._generate_filename("json")
        
        return json_bytes, "application/json; charset=utf-8", filename
