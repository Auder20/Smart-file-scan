from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.file_info import FileInfo
from app.api.routes_scanner import _scan_results

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


class FileInfoResponse(BaseModel):
    path: str
    name: str
    size: int
    extension: str
    category: str
    modified: str
    created: str
    hash: Optional[str] = None


class FilesListResponse(BaseModel):
    files: list[FileInfoResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool


@router.get("/{scan_id}")
def list_files(
    scan_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=1000),
    search: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    min_size: Optional[int] = Query(default=None),
    max_size: Optional[int] = Query(default=None)
) -> FilesListResponse:
    """Lista archivos de un escaneo con paginación y filtros"""
    
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    
    # Aplicar filtros
    filtered_files = result.files.copy()
    
    if search:
        search_lower = search.lower()
        filtered_files = [
            f for f in filtered_files 
            if search_lower in f.name.lower() or search_lower in f.path.lower()
        ]
    
    if category:
        filtered_files = [f for f in filtered_files if f.category.value == category]
    
    if min_size is not None:
        filtered_files = [f for f in filtered_files if f.size >= min_size]
    
    if max_size is not None:
        filtered_files = [f for f in filtered_files if f.size <= max_size]
    
    # Ordenar por tamaño (descendente)
    filtered_files.sort(key=lambda f: f.size, reverse=True)
    
    # Paginación
    total_count = len(filtered_files)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_files = filtered_files[start_idx:end_idx]
    
    # Convertir a respuesta
    file_responses = [
        FileInfoResponse(
            path=f.path,
            name=f.name,
            size=f.size,
            extension=f.extension,
            category=f.category.value,
            modified=f.modified.isoformat(),
            created=f.created.isoformat(),
            hash=f.hash
        )
        for f in page_files
    ]
    
    return FilesListResponse(
        files=file_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=end_idx < total_count
    )


@router.get("/{scan_id}/largest")
def get_largest_files(
    scan_id: str,
    limit: int = Query(default=10, ge=1, le=100)
) -> list[FileInfoResponse]:
    """Retorna los archivos más grandes de un escaneo"""
    
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    
    # Ordenar por tamaño y tomar los más grandes
    largest_files = sorted(result.files, key=lambda f: f.size, reverse=True)[:limit]
    
    return [
        FileInfoResponse(
            path=f.path,
            name=f.name,
            size=f.size,
            extension=f.extension,
            category=f.category.value,
            modified=f.modified.isoformat(),
            created=f.created.isoformat(),
            hash=f.hash
        )
        for f in largest_files
    ]


@router.get("/{scan_id}/extensions")
def get_extension_stats(scan_id: str) -> list[dict]:
    """Retorna estadísticas de extensiones de un escaneo"""
    
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    
    # Agrupar por extensión
    extension_stats = {}
    total_size = sum(f.size for f in result.files)
    
    for file in result.files:
        ext = file.extension.upper() if file.extension else "SIN EXTENSIÓN"
        
        if ext not in extension_stats:
            extension_stats[ext] = {
                "extension": ext,
                "count": 0,
                "total_size": 0,
                "percentage": 0.0
            }
        
        extension_stats[ext]["count"] += 1
        extension_stats[ext]["total_size"] += file.size
    
    # Calcular porcentajes
    for ext_stat in extension_stats.values():
        if total_size > 0:
            ext_stat["percentage"] = round(100 * ext_stat["total_size"] / total_size, 2)
    
    # Ordenar por tamaño total
    sorted_extensions = sorted(extension_stats.values(), key=lambda x: x["total_size"], reverse=True)
    
    return sorted_extensions


@router.get("/{scan_id}/categories")
def get_category_stats(scan_id: str) -> list[dict]:
    """Retorna estadísticas por categoría de un escaneo"""
    
    result = _scan_results.get(scan_id)
    if not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    
    # Agrupar por categoría
    category_stats = {}
    total_size = sum(f.size for f in result.files)
    
    for file in result.files:
        category = file.category.value
        
        if category not in category_stats:
            category_stats[category] = {
                "category": category,
                "count": 0,
                "total_size": 0,
                "percentage": 0.0
            }
        
        category_stats[category]["count"] += 1
        category_stats[category]["total_size"] += file.size
    
    # Calcular porcentajes
    for cat_stat in category_stats.values():
        if total_size > 0:
            cat_stat["percentage"] = round(100 * cat_stat["total_size"] / total_size, 2)
    
    # Ordenar por tamaño total
    sorted_categories = sorted(category_stats.values(), key=lambda x: x["total_size"], reverse=True)
    
    return sorted_categories
