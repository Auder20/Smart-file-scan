"""
Exporter factory for creating appropriate exporter instances.
"""

from __future__ import annotations

from typing import Type, Dict

from .base import BaseExporter
from .csv_exporter import CSVExporter
from .excel_exporter import ExcelExporter
from .json_exporter import JSONExporter
from .xml_exporter import XMLExporter


class ExporterFactory:
    """Factory class for creating exporters based on format type."""
    
    _exporters: Dict[str, Type[BaseExporter]] = {
        'csv': CSVExporter,
        'excel': ExcelExporter,
        'xlsx': ExcelExporter,
        'json': JSONExporter,
        'xml': XMLExporter
    }
    
    @classmethod
    def create_exporter(cls, format_type: str, scan_id: str) -> BaseExporter:
        """
        Create an exporter instance for the given format.
        
        Args:
            format_type: The export format ('csv', 'excel', 'json', 'xml')
            scan_id: The scan ID to export
            
        Returns:
            BaseExporter instance
            
        Raises:
            ValueError: If format_type is not supported
        """
        format_type = format_type.lower()
        
        if format_type not in cls._exporters:
            supported_formats = ', '.join(cls._exporters.keys())
            raise ValueError(f"Unsupported export format: {format_type}. "
                           f"Supported formats: {supported_formats}")
        
        exporter_class = cls._exporters[format_type]
        return exporter_class(scan_id)
    
    @classmethod
    def get_supported_formats(cls) -> list[str]:
        """Get list of supported export formats."""
        return list(cls._exporters.keys())
    
    @classmethod
    def register_exporter(cls, format_type: str, exporter_class: Type[BaseExporter]):
        """
        Register a new exporter type.
        
        Args:
            format_type: The format identifier
            exporter_class: The exporter class to register
        """
        cls._exporters[format_type.lower()] = exporter_class
