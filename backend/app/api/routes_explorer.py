from __future__ import annotations

import os
import logging
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/explorer", tags=["explorer"])


class FolderInfo(BaseModel):
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    file_count: Optional[int] = None


class AvailableDrive(BaseModel):
    name: str
    path: str
    total_space: Optional[int] = None
    free_space: Optional[int] = None


@router.get("/drives")
def get_available_drives() -> List[AvailableDrive]:
    """Retorna las unidades/dispositivos disponibles para escanear"""
    
    drives = []
    host_root = os.getenv("HOST_ROOT", "/host")
    
    if os.path.exists(host_root):
        # Listar directorios montados en /host
        for item in os.listdir(host_root):
            item_path = os.path.join(host_root, item)
            if os.path.isdir(item_path):
                try:
                    stat = os.statvfs(item_path)
                    total_space = stat.f_frsize * stat.f_blocks
                    free_space = stat.f_frsize * stat.f_bavail
                    
                    drives.append(AvailableDrive(
                        name=item.upper(),
                        path=item_path,
                        total_space=total_space,
                        free_space=free_space
                    ))
                except Exception as e:
                    logger.warning(f"No se puede obtener espacio de {item_path}: {e}")
                    drives.append(AvailableDrive(
                        name=item.upper(),
                        path=item_path
                    ))
    
    # Si no hay montajes, usar rutas por defecto
    if not drives:
        default_paths = [
            ("Users", "/host/users"),
            ("Data", "/host/data"),
            ("Home", "/host/home"),
            ("Temp", "/app/scans")
        ]
        
        for name, path in default_paths:
            if os.path.exists(path):
                drives.append(AvailableDrive(name=name, path=path))
    
    return drives


@router.get("/folders")
def explore_folders(
    path: str = Query(..., description="Ruta a explorar"),
    include_hidden: bool = Query(default=False),
    max_depth: int = Query(default=3, ge=1, le=10)
) -> List[FolderInfo]:
    """Explora carpetas en una ruta específica"""
    
    # Validar que la ruta sea segura
    host_root = os.getenv("HOST_ROOT", "/host")
    if not path.startswith(host_root) and not path.startswith("/app/scans"):
        raise HTTPException(400, detail="Ruta no permitida por seguridad")
    
    if not os.path.exists(path):
        raise HTTPException(404, detail=f"La ruta '{path}' no existe")
    
    folders = []
    
    try:
        for item in os.listdir(path):
            if not include_hidden and item.startswith('.'):
                continue
                
            item_path = os.path.join(path, item)
            
            try:
                is_dir = os.path.isdir(item_path)
                stat_info = os.stat(item_path)
                
                folder_info = FolderInfo(
                    name=item,
                    path=item_path,
                    is_directory=is_dir
                )
                
                if is_dir:
                    # Contar archivos y calcular tamaño
                    file_count = 0
                    total_size = 0
                    try:
                        for root, dirs, files in os.walk(item_path):
                            # Limitar profundidad
                            current_depth = root.replace(path, "").count(os.sep)
                            if current_depth >= max_depth:
                                dirs[:] = []  # No seguir explorando subdirectorios
                                continue
                            
                            file_count += len(files)
                            for file in files:
                                try:
                                    file_path = os.path.join(root, file)
                                    total_size += os.path.getsize(file_path)
                                except (OSError, PermissionError):
                                    continue
                    except (OSError, PermissionError):
                        pass
                    
                    folder_info.file_count = file_count
                    folder_info.size = total_size
                else:
                    folder_info.size = stat_info.st_size
                
                folders.append(folder_info)
                
            except (OSError, PermissionError) as e:
                logger.warning(f"Error accediendo a {item_path}: {e}")
                continue
                
    except (OSError, PermissionError) as e:
        raise HTTPException(403, detail=f"No se puede acceder a la ruta: {e}")
    
    # Ordenar: directorios primero, luego archivos, ambos por nombre
    folders.sort(key=lambda x: (not x.is_directory, x.name.lower()))
    
    return folders


@router.get("/common-folders")
def get_common_folders() -> List[FolderInfo]:
    """Retorna carpetas comunes para escanear rápidamente"""
    
    host_root = os.getenv("HOST_ROOT", "/host")
    common_folders = []
    
    # Carpetas típicas de Windows
    common_paths = [
        ("Documents", f"{host_root}/users/*/Documents"),
        ("Downloads", f"{host_root}/users/*/Downloads"),
        ("Desktop", f"{host_root}/users/*/Desktop"),
        ("Pictures", f"{host_root}/users/*/Pictures"),
        ("Videos", f"{host_root}/users/*/Videos"),
        ("Music", f"{host_root}/users/*/Music"),
        ("Projects", f"{host_root}/data/Projects"),
        ("Work", f"{host_root}/data/Work"),
    ]
    
    import glob
    
    for name, pattern in common_paths:
        try:
            matches = glob.glob(pattern)
            for match in matches[:3]:  # Limitar a 3 coincidencias por tipo
                if os.path.exists(match):
                    file_count = len([f for f in os.listdir(match) 
                                   if os.path.isfile(os.path.join(match, f))])
                    
                    common_folders.append(FolderInfo(
                        name=f"{name} ({os.path.basename(os.path.dirname(match))})",
                        path=match,
                        is_directory=True,
                        file_count=file_count
                    ))
        except Exception as e:
            logger.warning(f"Error buscando {pattern}: {e}")
    
    return common_folders


@router.get("/validate-path")
def validate_scan_path(path: str = Query(...)) -> dict:
    """Valida si una ruta es apta para escaneo"""
    
    host_root = os.getenv("HOST_ROOT", "/host")
    
    # Validaciones de seguridad
    if not path.startswith(host_root) and not path.startswith("/app/scans"):
        return {
            "valid": False,
            "reason": "Ruta no permitida por seguridad",
            "suggestion": "Usa rutas bajo /host/users o /host/data"
        }
    
    if not os.path.exists(path):
        return {
            "valid": False,
            "reason": "La ruta no existe",
            "suggestion": "Verifica que la ruta sea correcta"
        }
    
    if not os.path.isdir(path):
        return {
            "valid": False,
            "reason": "La ruta no es un directorio",
            "suggestion": "Selecciona una carpeta, no un archivo"
        }
    
    # Verificar permisos
    try:
        test_file = os.path.join(path, ".access_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        
        # Contar archivos estimados
        file_count = sum(len(files) for _, _, files in os.walk(path))
        
        return {
            "valid": True,
            "estimated_files": file_count,
            "readable": True,
            "writable": True,
            "message": "Ruta válida para escaneo"
        }
        
    except PermissionError:
        return {
            "valid": False,
            "reason": "Permisos insuficientes",
            "suggestion": "Verifica los permisos de la carpeta"
        }
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Error desconocido: {str(e)}",
            "suggestion": "Intenta con otra carpeta"
        }
