"""
Refactored export routes using the new exporter modules.

This replaces the original 1,517-line routes_export.py with a modular,
maintainable architecture using separate exporter classes.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.export.factory import ExporterFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/formats")
def get_supported_formats() -> dict:
    """Get list of supported export formats."""
    return {
        "formats": ExporterFactory.get_supported_formats(),
        "default": "csv"
    }


@router.get("/{scan_id}/{format}")
def export_scan(
    scan_id: str, 
    format: Literal["csv", "excel", "json", "xml"] = Query(..., description="Export format")
) -> StreamingResponse:
    """
    Export scan results in the specified format.
    
    Args:
        scan_id: The scan ID to export
        format: Export format (csv, excel, json, xml)
        
    Returns:
        StreamingResponse with the exported data
    """
    try:
        exporter = ExporterFactory.create_exporter(format, scan_id)
        content_generator, media_type, filename = exporter.export()
        
        # Handle CSV streaming differently
        if format.lower() == 'csv':
            return StreamingResponse(
                content_generator, 
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        else:
            # For other formats, return the bytes directly
            return StreamingResponse(
                iter([content_generator]),
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export error for scan {scan_id}, format {format}: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/{scan_id}")
def export_scan_default(scan_id: str) -> StreamingResponse:
    """
    Export scan results in default format (CSV).
    
    Args:
        scan_id: The scan ID to export
        
    Returns:
        StreamingResponse with CSV data
    """
    return export_scan(scan_id, "csv")
