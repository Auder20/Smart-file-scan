"""
XML exporter for scan results.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Tuple

from .base import BaseExporter


class XMLExporter(BaseExporter):
    """Export scan results to XML format."""
    
    def export(self) -> Tuple[bytes, str, str]:
        """Export scan data to XML format."""
        
        # Create root element
        root = ET.Element("scan_report")
        root.set("scan_id", self.meta["scan_id"])
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "root_path").text = self.meta["root_path"]
        ET.SubElement(metadata, "scanned_at").text = self.meta["scanned_at"]
        ET.SubElement(metadata, "total_files").text = str(self.meta["total_files"])
        ET.SubElement(metadata, "total_size").text = str(self.meta["total_size"])
        ET.SubElement(metadata, "duration_sec").text = str(self.meta["duration_sec"])
        
        # Add categories
        categories_elem = ET.SubElement(root, "categories")
        for category in self._get_categories():
            cat_elem = ET.SubElement(categories_elem, "category")
            cat_elem.set("name", category["category"])
            cat_elem.set("file_count", str(category["file_count"]))
            cat_elem.set("total_size", str(category["total_size"]))
            cat_elem.set("percentage", str(category["percentage"]))
        
        # Add files
        files_elem = ET.SubElement(root, "files")
        for file_data in self._iter_files():
            file_elem = ET.SubElement(files_elem, "file")
            ET.SubElement(file_elem, "name").text = file_data["name"]
            ET.SubElement(file_elem, "path").text = file_data["path"]
            ET.SubElement(file_elem, "size").text = str(file_data["size"])
            ET.SubElement(file_elem, "extension").text = file_data["extension"]
            ET.SubElement(file_elem, "category").text = file_data["category"]
            ET.SubElement(file_elem, "modified").text = file_data["modified"]
        
        # Pretty print XML
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
        
        filename = self._generate_filename("xml")
        
        return pretty_xml, "application/xml; charset=utf-8", filename
