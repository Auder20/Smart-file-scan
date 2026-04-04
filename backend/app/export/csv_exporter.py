"""
CSV exporter for scan results.
"""

from __future__ import annotations

import csv
import io
from typing import Tuple

from .base import BaseExporter


class CSVExporter(BaseExporter):
    """Export scan results to CSV format with streaming support."""
    
    def export(self) -> Tuple[bytes, str, str]:
        """Export scan data to CSV format."""
        
        def generate() -> bytes:
            """Generate CSV content as bytes."""
            buf = io.StringIO()
            writer = csv.writer(buf)
            
            # Write metadata header
            writer.writerow(["# Smart File Organizer — Reporte de Escaneo"])
            writer.writerow(["# Ruta escaneada", self.meta["root_path"]])
            writer.writerow(["# Fecha", self.meta["scanned_at"]])
            writer.writerow(["# Total archivos", self.meta["total_files"]])
            writer.writerow(["# Tamaño total", self._fmt_size(self.meta["total_size"])])
            writer.writerow(["# Duración (s)", self.meta["duration_sec"]])
            writer.writerow([])  # Empty row
            
            # Write column headers
            writer.writerow([
                "Nombre", "Ruta", "Tamaño (bytes)", "Tamaño", 
                "Extensión", "Categoría", "Modificado"
            ])
            
            # Yield header
            yield buf.getvalue().encode("utf-8-sig")
            
            # Write file data
            for file_data in self._iter_files():
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow([
                    file_data["name"], 
                    file_data["path"], 
                    file_data["size"], 
                    self._fmt_size(file_data["size"]),
                    file_data["extension"], 
                    file_data["category"], 
                    file_data["modified"]
                ])
                yield buf.getvalue().encode("utf-8-sig")
        
        # Generate filename and return
        filename = self._generate_filename("csv")
        
        # For streaming response, we'll return the generator directly
        # The calling code will handle the streaming
        return generate(), "text/csv; charset=utf-8", filename
