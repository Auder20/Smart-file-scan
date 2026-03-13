from __future__ import annotations

import os
import logging
import platform
import ctypes
from typing import List, Optional, Dict, Any
from pathlib import Path

import psutil
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
    used_space: Optional[int] = None
    filesystem: Optional[str] = None
    is_removable: bool = False


def _is_hidden(entry: os.DirEntry) -> bool:
    """Check if a file/directory is hidden on the current OS"""
    if platform.system() == "Windows":
        try:
            # Use FILE_ATTRIBUTE_HIDDEN via ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(entry.path)
            return attrs != 0xFFFFFFFF and (attrs & 2)  # FILE_ATTRIBUTE_HIDDEN = 2
        except:
            return False
    else:
        # Linux/macOS: check for dot prefix
        return entry.name.startswith('.')


def _is_removable(partition: psutil._common.sdiskpart) -> bool:
    """Check if a partition is removable (USB/external)"""
    if platform.system() == "Windows":
        try:
            # On Windows, check if it's a removable drive
            drive_letter = partition.device.split(':')[0]
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive_letter}:\\")
            return drive_type == 2  # DRIVE_REMOVABLE
        except:
            return False
    else:
        # Linux/macOS: use device name heuristics
        device = partition.device.lower()
        removable_indicators = ['usb', 'sd', 'mmc', 'external', 'removable']
        return any(indicator in device for indicator in removable_indicators)


def _is_blocked(path: str) -> bool:
    """Check if a path is in the blocked system paths list"""
    normalized_path = os.path.normpath(path).lower()
    
    if platform.system() == "Windows":
        blocked = [
            "c:\\windows\\system32",
            "c:\\windows\\syswow64", 
            "c:\\$recycle.bin",
            "c:\\system volume information"
        ]
    elif platform.system() == "Linux":
        blocked = ["/proc", "/sys", "/dev", "/run"]
    else:  # macOS
        blocked = ["/system", "/private/var/vm", "/dev"]
    
    return any(normalized_path.startswith(blocked.lower()) for blocked in blocked)


def _resolve_path_for_docker(path: str) -> str:
    """Translate real OS paths to /host/X paths for Docker mode"""
    host_root = os.getenv("HOST_ROOT")
    if not host_root:
        # Native mode: return path unchanged
        return path
    
    # Docker mode: translate to /host/X format
    if platform.system() == "Windows":
        # C:\Users\X -> /host/c/Users/X
        if len(path) >= 2 and path[1] == ':':
            drive = path[0].lower()
            rest_path = path[2:].replace('\\', '/')
            return f"{host_root}/{drive}{rest_path}"
    else:
        # Linux/macOS: /home/x -> /host/home/x
        if path.startswith('/'):
            return f"{host_root}{path}"
    
    return path


@router.get("/drives")
def get_available_drives() -> List[AvailableDrive]:
    """Retorna las unidades/dispositivos disponibles para escanear"""
    
    drives = []
    
    # Blocklist of filesystem types to skip
    SKIP_FSTYPES = {
        "squashfs", "tmpfs", "devtmpfs", "overlay", "aufs",
        "proc", "sysfs", "cgroup", "cgroup2", "pstore",
        "bpf", "tracefs", "debugfs", "securityfs", "hugetlbfs",
        "mqueue", "fusectl", "fuse.portal"
    }
    
    try:
        # Use psutil to detect all real drives/partitions
        partitions = psutil.disk_partitions(all=False)
        
        # Deduplicate by device, keeping the most specific mountpoint
        device_partitions = {}
        for partition in partitions:
            # Skip virtual filesystems and unwanted devices
            if (partition.fstype in SKIP_FSTYPES or
                partition.device.startswith('/dev/loop') or
                partition.device.startswith('/dev/sr') or
                partition.mountpoint.startswith('/snap') or
                partition.mountpoint.startswith('/boot') or
                partition.mountpoint.startswith('/sys') or
                partition.mountpoint.startswith('/proc')):
                continue
            
            device = partition.device
            current_mountpoint = partition.mountpoint
            
            # Keep the partition with the longest/most specific mountpoint
            if (device not in device_partitions or 
                len(current_mountpoint) > len(device_partitions[device].mountpoint)):
                device_partitions[device] = partition
        
        # Process deduplicated partitions
        for partition in device_partitions.values():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                
                # Format display name using mountpoint, not device
                display_name = partition.mountpoint
                if partition.fstype:
                    display_name += f" [{partition.fstype}]"
                
                drive = AvailableDrive(
                    name=display_name,  # Use mountpoint as display name
                    path=partition.mountpoint,
                    total_space=usage.total,
                    free_space=usage.free,
                    used_space=usage.used,
                    filesystem=partition.fstype,
                    is_removable=_is_removable(partition)
                )
                drives.append(drive)
                
            except Exception as e:
                logger.warning(f"Cannot get usage for {partition.mountpoint}: {e}")
                # Still add drive with basic info
                display_name = partition.mountpoint
                if partition.fstype:
                    display_name += f" [{partition.fstype}]"
                
                drive = AvailableDrive(
                    name=display_name,  # Use mountpoint as display name
                    path=partition.mountpoint,
                    filesystem=partition.fstype,
                    is_removable=_is_removable(partition)
                )
                drives.append(drive)
                
    except Exception as e:
        logger.error(f"Error detecting drives: {e}")
        # Fallback to basic root paths
        if platform.system() == "Windows":
            fallback_paths = ["C:\\", "D:\\"]
        else:
            fallback_paths = ["/"]
        
        for path in fallback_paths:
            if os.path.exists(path):
                drives.append(AvailableDrive(name=path, path=path))
    
    return drives


@router.get("/folders")
def explore_folders(
    path: str = Query(..., description="Ruta a explorar"),
    include_hidden: bool = Query(default=False)
) -> List[FolderInfo]:
    """Explora carpetas en una ruta específica usando os.scandir para速度快"""
    
    # Resolve path for Docker mode if needed
    resolved_path = _resolve_path_for_docker(path)
    
    if not os.path.exists(resolved_path):
        raise HTTPException(404, detail=f"La ruta '{path}' no existe")
    
    folders = []
    
    try:
        with os.scandir(resolved_path) as entries:
            for entry in entries:
                if not include_hidden and _is_hidden(entry):
                    continue
                
                try:
                    folder_info = FolderInfo(
                        name=entry.name,
                        path=path,  # Return original OS path, not resolved path
                        is_directory=entry.is_dir()
                    )
                    
                    if entry.is_dir():
                        # Quick file count without deep recursion
                        try:
                            with os.scandir(entry.path) as sub_entries:
                                file_count = len([e for e in sub_entries if e.is_file()])
                            folder_info.file_count = file_count
                        except (OSError, PermissionError):
                            folder_info.file_count = 0
                    else:
                        try:
                            folder_info.size = entry.stat().st_size
                        except (OSError, PermissionError):
                            folder_info.size = 0
                    
                    folders.append(folder_info)
                    
                except (OSError, PermissionError) as e:
                    logger.debug(f"Error accessing {entry.path}: {e}")
                    # Add with limited access label
                    try:
                        folders.append(FolderInfo(
                            name=entry.name + " (sin acceso)",
                            path=path,
                            is_directory=entry.is_dir()
                        ))
                    except:
                        continue
                        
    except (OSError, PermissionError) as e:
        raise HTTPException(403, detail=f"No se puede acceder a la ruta: {e}")
    
    # Sort: directories first, then files, both by name
    folders.sort(key=lambda x: (not x.is_directory, x.name.lower()))
    
    return folders


@router.get("/validate-path")
def validate_scan_path(path: str = Query(...)) -> dict:
    """Valida si una ruta es apta para escaneo"""
    
    if not os.path.isabs(path):
        return {
            "valid": False,
            "reason": "La ruta debe ser absoluta",
            "suggestion": "Usa rutas absolutas como C:\\Users o /home/user"
        }
    
    if _is_blocked(path):
        return {
            "valid": False,
            "reason": "Ruta del sistema bloqueada por seguridad",
            "suggestion": "Selecciona carpetas de usuario o datos"
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
    
    # Check read permissions
    try:
        os.listdir(path)
        readable = True
    except PermissionError:
        return {
            "valid": False,
            "reason": "Sin permisos de lectura",
            "suggestion": "Selecciona una carpeta con permisos de lectura"
        }
    
    # Check write permissions (optional for scanning)
    try:
        test_file = os.path.join(path, ".access_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        writable = True
    except PermissionError:
        writable = False
    except Exception as e:
        logger.warning(f"Error checking write permissions for {path}: {e}")
        writable = False
    
    # Quick file count estimation
    try:
        file_count = 0
        for root, dirs, files in os.walk(path):
            try:
                file_count += len(files)
            except PermissionError:
                continue
        
        message = "Ruta válida para escaneo" if writable else "Ruta de solo lectura (escaneo limitado)"
        
        return {
            "valid": True,
            "estimated_files": file_count,
            "readable": readable,
            "writable": writable,
            "message": message,
            "warning": None if writable else "Algunas funciones pueden estar limitadas en carpetas de solo lectura"
        }
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Error analizando la carpeta: {str(e)}",
            "suggestion": "Intenta con otra carpeta"
        }
