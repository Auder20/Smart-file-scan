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


def _translate_path_from_docker(docker_path: str) -> str:
    """Translate /host/X paths back to native OS format for frontend consumption"""
    host_root = os.getenv("HOST_ROOT")
    if not host_root or not docker_path.startswith(host_root):
        return docker_path
    
    relative_path = docker_path[len(host_root):]
    
    if platform.system() == "Windows":
        # /c/Users/John -> C:\Users\John
        if len(relative_path) >= 2 and relative_path[1] == '/':
            drive_letter = relative_path[1].upper()
            rest_path = relative_path[2:].replace('/', '\\')
            return f"{drive_letter}:\\{rest_path}"
    else:
        # Linux/macOS: path is already correct
        return relative_path
    
    return docker_path


@router.get("/drives")
def get_available_drives() -> List[AvailableDrive]:
    """Retorna las unidades/dispositivos disponibles para escanear"""
    
    drives = []
    host_root = os.getenv("HOST_ROOT")
    is_docker_mode = host_root is not None
    
    # Blocklist of filesystem types to skip
    SKIP_FSTYPES = {
        "squashfs", "tmpfs", "devtmpfs", "overlay", "aufs",
        "proc", "sysfs", "cgroup", "cgroup2", "pstore",
        "bpf", "tracefs", "debugfs", "securityfs", "hugetlbfs",
        "mqueue", "fusectl", "fuse.portal"
    }
    
    try:
        # IMPROVEMENT: In Docker mode, scan the /host directory for available drives
        if is_docker_mode and os.path.exists(host_root):
            logger.info(f"Docker mode detected, scanning {host_root} for available drives")
            
            # Scan for Windows-style drives (e.g., /host/c, /host/d)
            if os.path.exists(host_root):
                try:
                    host_entries = os.listdir(host_root)
                    for entry in host_entries:
                        entry_path = os.path.join(host_root, entry)
                        if not os.path.isdir(entry_path):
                            continue
                        
                        # Check for Windows drive letters (single character directories)
                        if len(entry) == 1 and entry.isalpha():
                            # This is a Windows drive letter (e.g., c, d, e)
                            drive_letter = entry.upper()
                            native_path = f"{drive_letter}:\\"
                            docker_path = entry_path
                            
                            # Also check for longer paths like /host/parent-distro/mnt/host/wsl/
                            # These are WSL mounts
                            if entry.lower() in ['mnt', 'media', 'volumes']:
                                # Recursively scan for more drives
                                _scan_for_drives_recursive(entry_path, drives, host_root, native_path.startswith("C:"), is_docker_mode)
                                continue
                            
                            try:
                                usage = psutil.disk_usage(docker_path)
                                drive = AvailableDrive(
                                    name=native_path,
                                    path=native_path,
                                    total_space=usage.total,
                                    free_space=usage.free,
                                    used_space=usage.used,
                                    filesystem="ntfs" if drive_letter in ['C', 'D'] else "unknown",
                                    is_removable=drive_letter not in ['C']
                                )
                            except:
                                drive = AvailableDrive(
                                    name=native_path,
                                    path=native_path,
                                    filesystem="unknown",
                                    is_removable=drive_letter not in ['C']
                                )
                            drives.append(drive)
                        
                        # Check for Linux-style mounts (e.g., /host/home, /host/media)
                        elif entry.lower() in ['home', 'media', 'mnt', 'Volumes']:
                            _scan_for_drives_recursive(entry_path, drives, host_root, False, is_docker_mode)
                            
                except Exception as e:
                    logger.warning(f"Error scanning host root: {e}")
            
            # If we found drives, return them
            if drives:
                # Sort drives: fixed drives first, then removable
                drives.sort(key=lambda d: (d.is_removable, d.name))
                return drives
        
        # Fallback: Use psutil for native mode or if host_root scan failed
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
                
                # FIX: In Docker mode, translate mountpoint to /host/X format
                display_path = partition.mountpoint
                api_path = partition.mountpoint
                
                if host_root and partition.mountpoint.startswith(host_root):
                    # This is a mounted host path, translate it back for the API
                    # /host/c/Users -> C:/Users (Windows) or /home/user (Linux)
                    relative_path = partition.mountpoint[len(host_root):]
                    if platform.system() == "Windows":
                        # /c/Users -> C:\Users
                        if len(relative_path) >= 2 and relative_path[1] == '/':
                            drive_letter = relative_path[1].upper()
                            rest_path = relative_path[2:].replace('/', '\\')
                            api_path = f"{drive_letter}:\\{rest_path}"
                            display_path = api_path
                    else:
                        # Linux/macOS: path is already correct
                        api_path = relative_path
                        display_path = relative_path
                elif host_root and not partition.mountpoint.startswith('/host'):
                    # Mount point inside container that's not under /host
                    # Try to check if it's accessible via /host
                    host_equivalent = f"{host_root}{partition.mountpoint}"
                    if os.path.exists(host_equivalent):
                        api_path = host_equivalent
                        display_path = partition.mountpoint
                
                # Format display name using mountpoint, not device
                display_name = display_path
                if partition.fstype:
                    display_name += f" [{partition.fstype}]"
                
                drive = AvailableDrive(
                    name=display_name,
                    path=api_path,  # Use translated path for API calls
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
                display_path = partition.mountpoint
                api_path = partition.mountpoint
                
                if host_root and partition.mountpoint.startswith(host_root):
                    relative_path = partition.mountpoint[len(host_root):]
                    if platform.system() == "Windows":
                        if len(relative_path) >= 2 and relative_path[1] == '/':
                            drive_letter = relative_path[1].upper()
                            rest_path = relative_path[2:].replace('/', '\\')
                            api_path = f"{drive_letter}:\\{rest_path}"
                            display_path = api_path
                    else:
                        api_path = relative_path
                        display_path = relative_path
                
                display_name = display_path
                if partition.fstype:
                    display_name += f" [{partition.fstype}]"
                
                drive = AvailableDrive(
                    name=display_name,
                    path=api_path,
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


def _scan_for_drives_recursive(base_path: str, drives_list: list, host_root: str, is_windows: bool, is_docker_mode: bool):
    """Recursively scan for drives in a directory structure"""
    try:
        entries = os.listdir(base_path)
        for entry in entries:
            entry_path = os.path.join(base_path, entry)
            if not os.path.isdir(entry_path):
                continue
            
            # Windows drive letters in WSL style (e.g., /host/mnt/c, /host/mnt/d)
            if len(entry) == 1 and entry.isalpha():
                drive_letter = entry.upper()
                native_path = f"{drive_letter}:\\"
                
                try:
                    usage = psutil.disk_usage(entry_path)
                    drive = AvailableDrive(
                        name=native_path,
                        path=native_path,
                        total_space=usage.total,
                        free_space=usage.free,
                        used_space=usage.used,
                        filesystem="ntfs" if drive_letter in ['C', 'D'] else "unknown",
                        is_removable=drive_letter not in ['C']
                    )
                except:
                    drive = AvailableDrive(
                        name=native_path,
                        path=native_path,
                        filesystem="unknown",
                        is_removable=drive_letter not in ['C']
                    )
                
                # Avoid duplicates
                if not any(d.path == native_path for d in drives_list):
                    drives_list.append(drive)
            
            # Linux mount points
            elif entry.lower() not in ['lost+found']:
                # Translate to native path
                if host_root and entry_path.startswith(host_root):
                    native_path = entry_path[len(host_root):]
                else:
                    native_path = entry_path
                
                try:
                    usage = psutil.disk_usage(entry_path)
                    drive = AvailableDrive(
                        name=native_path,
                        path=native_path,
                        total_space=usage.total,
                        free_space=usage.free,
                        used_space=usage.used,
                        filesystem="ext4",
                        is_removable='media' in entry_path.lower() or 'mnt' in entry_path.lower()
                    )
                except:
                    drive = AvailableDrive(
                        name=native_path,
                        path=native_path,
                        filesystem="unknown",
                        is_removable='media' in entry_path.lower() or 'mnt' in entry_path.lower()
                    )
                
                # Avoid duplicates
                if not any(d.path == native_path for d in drives_list):
                    drives_list.append(drive)
                    
    except Exception as e:
        logger.debug(f"Error in recursive scan: {e}")


@router.get("/folders")
def explore_folders(
    path: str = Query(..., description="Ruta a explorar"),
    include_hidden: bool = Query(default=False)
) -> List[FolderInfo]:
    """Explora carpetas en una ruta específica usando os.scandir para速度快"""
    
    # FIX: Handle Docker path translation properly
    # The path comes from the frontend in native OS format (e.g., C:\Users or /home/user)
    # We need to translate it to /host/X format for Docker access
    resolved_path = _resolve_path_for_docker(path)
    
    # Also try realpath for normalized path
    normalized_path = os.path.realpath(resolved_path)
    
    # Check if path is blocked system path
    if _is_blocked(normalized_path):
        raise HTTPException(403, detail=f"Acceso denegado a ruta del sistema: {path}")
    
    if not os.path.exists(normalized_path):
        # Try original path as fallback (for native mode)
        if not os.path.exists(path):
            raise HTTPException(404, detail=f"La ruta '{path}' no existe")
        normalized_path = path
    
    folders = []
    
    try:
        with os.scandir(normalized_path) as entries:
            for entry in entries:
                if not include_hidden and _is_hidden(entry):
                    continue
                
                try:
                    # Return the original path format to the frontend, not the /host/X format
                    # This ensures the frontend can use the paths correctly
                    return_path = entry.path
                    if os.getenv("HOST_ROOT") and entry.path.startswith(os.getenv("HOST_ROOT")):
                        # Translate back from /host/X to native format
                        return_path = _translate_path_from_docker(entry.path)
                    
                    folder_info = FolderInfo(
                        name=entry.name,
                        path=return_path,  # Return native format path to frontend
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
                        return_path = entry.path
                        if os.getenv("HOST_ROOT") and entry.path.startswith(os.getenv("HOST_ROOT")):
                            return_path = _translate_path_from_docker(entry.path)
                        
                        folders.append(FolderInfo(
                            name=entry.name + " (sin acceso)",
                            path=return_path,  # Return native format path to frontend
                            is_directory=entry.is_dir()
                        ))
                    except:
                        continue
                        
    except (OSError, PermissionError) as e:
        raise HTTPException(403, detail=f"No se puede acceder a la ruta: {e}")
    
    # Sort: directories first, then files, both by name
    folders.sort(key=lambda x: (not x.is_directory, x.name.lower()))
    
    return folders


@router.get("/debug/current-dir")
def get_current_dir() -> dict:
    """Endpoint de depuración para ver el directorio actual"""
    return {
        "current_dir": os.getcwd(),
        "pwd_env": os.getenv("PWD"),
        "host_root": os.getenv("HOST_ROOT"),
        "resolved_work_dir": "/host/parent-distro/mnt/host/wsl/docker-desktop-user-distro" if os.getenv("PWD") == "/app" else f"{os.getenv('HOST_ROOT')}{os.getenv('PWD', '')}"
    }

@router.get("/validate-path")
def validate_scan_path(path: str = Query(..., description="Ruta a validar")) -> dict:
    """Valida si una ruta es apta para escaneo"""
    
    # SEC 1: Normalize path and check for path traversal
    normalized_path = os.path.realpath(path)
    
    # Para Docker/WSL: permitir rutas relativas al directorio actual
    if os.getenv("HOST_ROOT") and not os.path.isabs(normalized_path):
        # Si es una ruta relativa en modo Docker, resolverla relativamente al directorio de trabajo del host
        # Usar el directorio de trabajo del backend como base para rutas relativas
        backend_work_dir = os.getenv("PWD", "/app")  # Directorio actual del contenedor
        # Mapear al directorio correspondiente en el host
        if backend_work_dir == "/app":
            host_work_dir = "/host/parent-distro/mnt/host/wsl/docker-desktop-user-distro"
        else:
            host_work_dir = f"{os.getenv('HOST_ROOT')}{backend_work_dir}"
        
        resolved_path = os.path.join(host_work_dir, normalized_path)
    else:
        resolved_path = _resolve_path_for_docker(normalized_path)
    
    if _is_blocked(resolved_path):
        return {
            "valid": False,
            "reason": "Ruta del sistema bloqueada por seguridad",
            "suggestion": "Selecciona carpetas de usuario o datos"
        }
    
    if not os.path.exists(resolved_path):
        return {
            "valid": False,
            "reason": "La ruta no existe",
            "suggestion": "Verifica que la ruta sea correcta"
        }
    
    if not os.path.isdir(resolved_path):
        return {
            "valid": False,
            "reason": "La ruta debe ser un directorio",
            "suggestion": "Selecciona una carpeta válida"
        }
    
    # Check read permissions
    try:
        os.listdir(resolved_path)
        readable = True
    except PermissionError:
        return {
            "valid": False,
            "reason": "Sin permisos de lectura",
            "suggestion": "Selecciona una carpeta con permisos de lectura"
        }
    
    # Check write permissions (optional for scanning)
    try:
        test_file = os.path.join(resolved_path, ".access_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        writable = True
    except PermissionError:
        writable = False
    except Exception as e:
        logger.warning(f"Error checking write permissions for {resolved_path}: {e}")
        writable = False
    
    # Quick file count estimation
    try:
        file_count = 0
        for root, dirs, files in os.walk(resolved_path):
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
