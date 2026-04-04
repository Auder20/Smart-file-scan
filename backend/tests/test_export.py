"""
Unit tests for export functionality.
"""

import pytest
import json
import csv
import io
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.export.factory import ExporterFactory
from app.export.csv_exporter import CSVExporter
from app.export.json_exporter import JSONExporter
from app.export.xml_exporter import XMLExporter
from app.export.excel_exporter import ExcelExporter


class TestExporterFactory:
    """Test the exporter factory."""
    
    def test_get_supported_formats(self):
        """Test getting supported formats."""
        formats = ExporterFactory.get_supported_formats()
        expected = ['csv', 'excel', 'xlsx', 'json', 'xml']
        assert set(formats) == set(expected)
    
    def test_create_csv_exporter(self):
        """Test creating CSV exporter."""
        exporter = ExporterFactory.create_exporter('csv', 'test_scan_id')
        assert isinstance(exporter, CSVExporter)
        assert exporter.scan_id == 'test_scan_id'
    
    def test_create_json_exporter(self):
        """Test creating JSON exporter."""
        exporter = ExporterFactory.create_exporter('json', 'test_scan_id')
        assert isinstance(exporter, JSONExporter)
        assert exporter.scan_id == 'test_scan_id'
    
    def test_create_xml_exporter(self):
        """Test creating XML exporter."""
        exporter = ExporterFactory.create_exporter('xml', 'test_scan_id')
        assert isinstance(exporter, XMLExporter)
        assert exporter.scan_id == 'test_scan_id'
    
    def test_create_excel_exporter(self):
        """Test creating Excel exporter."""
        exporter = ExporterFactory.create_exporter('excel', 'test_scan_id')
        assert isinstance(exporter, ExcelExporter)
        assert exporter.scan_id == 'test_scan_id'
    
    def test_create_excel_exporter_xlsx_alias(self):
        """Test creating Excel exporter with xlsx alias."""
        exporter = ExporterFactory.create_exporter('xlsx', 'test_scan_id')
        assert isinstance(exporter, ExcelExporter)
        assert exporter.scan_id == 'test_scan_id'
    
    def test_unsupported_format(self):
        """Test error for unsupported format."""
        with pytest.raises(ValueError, match="Unsupported export format"):
            ExporterFactory.create_exporter('pdf', 'test_scan_id')
    
    def test_case_insensitive_format(self):
        """Test case insensitive format creation."""
        exporter = ExporterFactory.create_exporter('CSV', 'test_scan_id')
        assert isinstance(exporter, CSVExporter)


class MockBaseExporter:
    """Mock base exporter for testing."""
    
    def __init__(self, scan_id: str):
        self.scan_id = scan_id
        self.meta = {
            "scan_id": scan_id,
            "root_path": "/test/path",
            "total_files": 100,
            "total_size": 1000000,
            "duration_sec": 60,
            "scanned_at": "2023-01-01T12:00:00"
        }
    
    def _iter_files(self):
        """Mock file iteration."""
        for i in range(3):
            yield {
                "name": f"file_{i}.txt",
                "path": f"/test/path/file_{i}.txt",
                "size": 1000 + i * 100,
                "extension": "txt",
                "category": "documents",
                "modified": "2023-01-01T12:00:00"
            }
    
    def _get_categories(self):
        """Mock category data."""
        return [
            {"category": "documents", "file_count": 3, "total_size": 3100, "percentage": 100.0}
        ]
    
    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        """Mock size formatting."""
        return f"{size_bytes} B"
    
    def _generate_filename(self, extension: str) -> str:
        """Mock filename generation."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"scan_{self.scan_id}_{timestamp}.{extension}"


class TestCSVExporter:
    """Test CSV exporter functionality."""
    
    @patch('app.export.csv_exporter.BaseExporter.__init__')
    @patch('app.export.csv_exporter.BaseExporter._iter_files')
    @patch('app.export.csv_exporter.BaseExporter._get_meta')
    def test_csv_export_structure(self, mock_meta, mock_iter_files, mock_init):
        """Test CSV export structure."""
        mock_init.return_value = None
        mock_meta.return_value = {
            "scan_id": "test123",
            "root_path": "/test/path",
            "total_files": 3,
            "total_size": 3100,
            "duration_sec": 60,
            "scanned_at": "2023-01-01T12:00:00"
        }
        
        mock_files = [
            {"name": "file1.txt", "path": "/test/file1.txt", "size": 1000,
             "extension": "txt", "category": "documents", "modified": "2023-01-01"},
            {"name": "file2.txt", "path": "/test/file2.txt", "size": 1100,
             "extension": "txt", "category": "documents", "modified": "2023-01-01"}
        ]
        mock_iter_files.return_value = iter(mock_files)
        
        exporter = CSVExporter("test123")
        exporter.meta = mock_meta.return_value
        
        content_gen, media_type, filename = exporter.export()
        
        assert media_type == "text/csv; charset=utf-8"
        assert filename.startswith("scan_test123_")
        assert filename.endswith(".csv")
        
        # Test CSV content generation
        content_bytes = b''.join(list(content_gen))
        content_str = content_bytes.decode('utf-8-sig')
        
        # Check header metadata
        assert "# Smart File Organizer — Reporte de Escaneo" in content_str
        assert "/test/path" in content_str
        assert "test123" in content_str
        
        # Check CSV headers
        assert "Nombre,Ruta,Tamaño (bytes),Tamaño,Extensión,Categoría,Modificado" in content_str
        
        # Check file data
        assert "file1.txt" in content_str
        assert "file2.txt" in content_str


class TestJSONExporter:
    """Test JSON exporter functionality."""
    
    @patch('app.export.json_exporter.BaseExporter.__init__')
    @patch('app.export.json_exporter.BaseExporter._iter_files')
    @patch('app.export.json_exporter.BaseExporter._get_meta')
    @patch('app.export.json_exporter.BaseExporter._get_categories')
    def test_json_export_structure(self, mock_categories, mock_meta, mock_iter_files, mock_init):
        """Test JSON export structure."""
        mock_init.return_value = None
        mock_meta.return_value = {
            "scan_id": "test123",
            "root_path": "/test/path",
            "total_files": 2,
            "total_size": 2100,
            "duration_sec": 60,
            "scanned_at": "2023-01-01T12:00:00"
        }
        
        mock_files = [
            {"name": "file1.txt", "path": "/test/file1.txt", "size": 1000,
             "extension": "txt", "category": "documents", "modified": "2023-01-01"}
        ]
        mock_iter_files.return_value = iter(mock_files)
        
        mock_categories.return_value = [
            {"category": "documents", "file_count": 1, "total_size": 1000, "percentage": 47.6}
        ]
        
        exporter = JSONExporter("test123")
        exporter.meta = mock_meta.return_value
        
        content_bytes, media_type, filename = exporter.export()
        
        assert media_type == "application/json; charset=utf-8"
        assert filename.startswith("scan_test123_")
        assert filename.endswith(".json")
        
        # Parse JSON content
        content_str = content_bytes.decode('utf-8')
        data = json.loads(content_str)
        
        # Check structure
        assert "metadata" in data
        assert "categories" in data
        assert "files" in data
        
        # Check metadata
        assert data["metadata"]["scan_id"] == "test123"
        assert data["metadata"]["root_path"] == "/test/path"
        assert data["metadata"]["total_files"] == 2
        
        # Check files
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "file1.txt"
        
        # Check categories
        assert len(data["categories"]) == 1
        assert data["categories"][0]["category"] == "documents"


class TestXMLExporter:
    """Test XML exporter functionality."""
    
    @patch('app.export.xml_exporter.BaseExporter.__init__')
    @patch('app.export.xml_exporter.BaseExporter._iter_files')
    @patch('app.export.xml_exporter.BaseExporter._get_meta')
    @patch('app.export.xml_exporter.BaseExporter._get_categories')
    def test_xml_export_structure(self, mock_categories, mock_meta, mock_iter_files, mock_init):
        """Test XML export structure."""
        mock_init.return_value = None
        mock_meta.return_value = {
            "scan_id": "test123",
            "root_path": "/test/path",
            "total_files": 1,
            "total_size": 1000,
            "duration_sec": 60,
            "scanned_at": "2023-01-01T12:00:00"
        }
        
        mock_files = [
            {"name": "file1.txt", "path": "/test/file1.txt", "size": 1000,
             "extension": "txt", "category": "documents", "modified": "2023-01-01"}
        ]
        mock_iter_files.return_value = iter(mock_files)
        
        mock_categories.return_value = [
            {"category": "documents", "file_count": 1, "total_size": 1000, "percentage": 100.0}
        ]
        
        exporter = XMLExporter("test123")
        exporter.meta = mock_meta.return_value
        
        content_bytes, media_type, filename = exporter.export()
        
        assert media_type == "application/xml; charset=utf-8"
        assert filename.startswith("scan_test123_")
        assert filename.endswith(".xml")
        
        # Parse XML content
        content_str = content_bytes.decode('utf-8')
        
        # Check XML structure
        assert "<scan_report" in content_str
        assert 'scan_id="test123"' in content_str
        assert "<metadata>" in content_str
        assert "<root_path>/test/path</root_path>" in content_str
        assert "<categories>" in content_str
        assert "<files>" in content_str
        assert "<file>" in content_str
        assert "<name>file1.txt</name>" in content_str


@pytest.mark.skipif(True, reason="Excel tests require openpyxl installation")
class TestExcelExporter:
    """Test Excel exporter functionality."""
    
    @patch('app.export.excel_exporter.BaseExporter.__init__')
    @patch('app.export.excel_exporter.BaseExporter._iter_files')
    @patch('app.export.excel_exporter.BaseExporter._get_meta')
    @patch('app.export.excel_exporter.BaseExporter._get_categories')
    def test_excel_export_structure(self, mock_categories, mock_meta, mock_iter_files, mock_init):
        """Test Excel export structure."""
        pytest.importorskip("openpyxl")
        
        mock_init.return_value = None
        mock_meta.return_value = {
            "scan_id": "test123",
            "root_path": "/test/path",
            "total_files": 1,
            "total_size": 1000,
            "duration_sec": 60,
            "scanned_at": "2023-01-01T12:00:00"
        }
        
        mock_files = [
            {"name": "file1.txt", "path": "/test/file1.txt", "size": 1000,
             "extension": "txt", "category": "documents", "modified": "2023-01-01"}
        ]
        mock_iter_files.return_value = iter(mock_files)
        
        mock_categories.return_value = [
            {"category": "documents", "file_count": 1, "total_size": 1000, "percentage": 100.0}
        ]
        
        exporter = ExcelExporter("test123")
        exporter.meta = mock_meta.return_value
        
        content_bytes, media_type, filename = exporter.export()
        
        assert media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert filename.startswith("scan_test123_")
        assert filename.endswith(".xlsx")
        
        # Check that content is non-empty binary data
        assert len(content_bytes) > 0
        # Excel files have a specific signature
        assert content_bytes.startswith(b'PK\x03\x04')


if __name__ == "__main__":
    pytest.main([__file__])
