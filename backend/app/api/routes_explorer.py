from __future__ import annotations

import os
import logging
import platform
import ctypes
from typing import List, Optional

import psutil
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# FIX: importar desde core/path_utils para no duplicar lógica
# ni generar dependencias circulares con file_info.py
from app.core.path_utils import (
    resolve_path_for_docker,
    translate_path_from_docker,
    is_blocked_path,
)

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
    if platform.system() == "Windows":
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(entry.path)
            return attrs != 0xFFFFFFFF and (attrs & 2)
        except Exception:
            return False
    return entry.name.startswith(".")


def _is_removable(partition: psutil._common.sdiskpart) -> bool:
    if platform.system() == "Windows":
        try:
            drive_letter = partition.device.split(":")[0]
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive_letter}:\\")
            return drive_type == 2
        except Exception:
            return False
    device = partition.device.lower()
    return any(k in device for k in ["usb", "sd", "mmc", "external", "removable"])


# ---------------------------------------------------------------------------
# Alias público para retrocompatibilidad con cualquier módulo que ya importara
# _resolve_path_for_docker desde este archivo (no debe haber ninguno ahora,
# pero se mantiene por si acaso).
# ---------------------------------------------------------------------------
_resolve_path_for_docker = resolve_path_for_docker


# ---------------------------------------------------------------------------
# Drives
# ---------------------------------------------------------------------------

SKIP_FSTYPES = {
    "squashfs", "tmpfs", "devtmpfs", "overlay", "aufs",
    "proc", "sysfs", "cgroup", "cgroup2", "pstore",
    "bpf", "tracefs", "debugfs", "securityfs", "hugetlbfs",
    "mqueue", "fusectl", "fuse.portal",
}


@router.get("/drives")
def get_available_drives() -> List[AvailableDrive]:
    drives: list[AvailableDrive] = []
    host_root = os.getenv("HOST_ROOT")
    is_docker_mode = host_root is not None

    try:
        if is_docker_mode and host_root and os.path.exists(host_root):
            logger.info(f"Docker mode: scanning {host_root} for drives")
            try:
                for entry in os.listdir(host_root):
                    entry_path = os.path.join(host_root, entry)
                    if not os.path.isdir(entry_path):
                        continue

                    if len(entry) == 1 and entry.isalpha():
                        drive_letter = entry.upper()
                        native_path = f"{drive_letter}:\\"
                        try:
                            usage = psutil.disk_usage(entry_path)
                            drive = AvailableDrive(
                                name=native_path, path=native_path,
                                total_space=usage.total, free_space=usage.free,
                                used_space=usage.used,
                                filesystem="ntfs" if drive_letter in ("C", "D") else "unknown",
                                is_removable=drive_letter not in ("C",),
                            )
                        except Exception:
                            drive = AvailableDrive(name=native_path, path=native_path)
                        drives.append(drive)

                    elif entry.lower() in ("home", "media", "mnt", "Volumes"):
                        _scan_for_drives_recursive(entry_path, drives, host_root, False, is_docker_mode)
            except Exception as e:
                logger.warning(f"Error scanning host root: {e}")

            if drives:
                drives.sort(key=lambda d: (d.is_removable, d.name))
                return drives

        partitions = psutil.disk_partitions(all=False)
        device_partitions: dict = {}
        for p in partitions:
            if (
                p.fstype in SKIP_FSTYPES
                or p.device.startswith("/dev/loop")
                or p.device.startswith("/dev/sr")
                or p.mountpoint.startswith(("/snap", "/boot", "/sys", "/proc"))
            ):
                continue
            if (p.device not in device_partitions or
                    len(p.mountpoint) > len(device_partitions[p.device].mountpoint)):
                device_partitions[p.device] = p

        for partition in device_partitions.values():
            api_path = partition.mountpoint
            if host_root and partition.mountpoint.startswith(host_root):
                relative = partition.mountpoint[len(host_root):]
                if platform.system() == "Windows" and len(relative) >= 2 and relative[1] == "/":
                    drive_letter = relative[0].upper()
                    api_path = f"{drive_letter}:\\" + relative[2:].replace("/", "\\")
                else:
                    api_path = relative

            display_name = api_path
            if partition.fstype:
                display_name += f" [{partition.fstype}]"

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append(AvailableDrive(
                    name=display_name, path=api_path,
                    total_space=usage.total, free_space=usage.free,
                    used_space=usage.used, filesystem=partition.fstype,
                    is_removable=_is_removable(partition),
                ))
            except Exception:
                drives.append(AvailableDrive(
                    name=display_name, path=api_path,
                    filesystem=partition.fstype,
                    is_removable=_is_removable(partition),
                ))

    except Exception as e:
        logger.error(f"Error detecting drives: {e}")
        fallback = ["C:\\", "D:\\"] if platform.system() == "Windows" else ["/"]
        for fp in fallback:
            if os.path.exists(fp):
                drives.append(AvailableDrive(name=fp, path=fp))

    return drives


def _scan_for_drives_recursive(
    base_path: str, drives_list: list, host_root: str,
    is_windows: bool, is_docker_mode: bool
) -> None:
    try:
        for entry in os.listdir(base_path):
            entry_path = os.path.join(base_path, entry)
            if not os.path.isdir(entry_path):
                continue

            if len(entry) == 1 and entry.isalpha():
                drive_letter = entry.upper()
                native_path = f"{drive_letter}:\\"
                try:
                    usage = psutil.disk_usage(entry_path)
                    drive = AvailableDrive(
                        name=native_path, path=native_path,
                        total_space=usage.total, free_space=usage.free,
                        used_space=usage.used,
                        filesystem="ntfs" if drive_letter in ("C", "D") else "unknown",
                        is_removable=drive_letter not in ("C",),
                    )
                except Exception:
                    drive = AvailableDrive(name=native_path, path=native_path)
                if not any(d.path == native_path for d in drives_list):
                    drives_list.append(drive)

            elif entry.lower() not in ("lost+found",):
                native_path = (
                    entry_path[len(host_root):]
                    if host_root and entry_path.startswith(host_root)
                    else entry_path
                )
                try:
                    usage = psutil.disk_usage(entry_path)
                    drive = AvailableDrive(
                        name=native_path, path=native_path,
                        total_space=usage.total, free_space=usage.free,
                        used_space=usage.used, filesystem="ext4",
                        is_removable="media" in entry_path.lower() or "mnt" in entry_path.lower(),
                    )
                except Exception:
                    drive = AvailableDrive(name=native_path, path=native_path)
                if not any(d.path == native_path for d in drives_list):
                    drives_list.append(drive)
    except Exception as e:
        logger.debug(f"Error in recursive scan: {e}")


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

@router.get("/folders")
def explore_folders(
    path: str = Query(..., description="Ruta a explorar"),
    include_hidden: bool = Query(default=False),
) -> List[FolderInfo]:
    resolved_path = resolve_path_for_docker(path)
    normalized_path = os.path.realpath(resolved_path)

    if is_blocked_path(normalized_path):
        raise HTTPException(403, detail=f"Acceso denegado a ruta del sistema: {path}")

    if not os.path.exists(normalized_path):
        if not os.path.exists(path):
            raise HTTPException(404, detail=f"La ruta '{path}' no existe")
        normalized_path = path

    folders: list[FolderInfo] = []
    host_root = os.getenv("HOST_ROOT")

    try:
        with os.scandir(normalized_path) as entries:
            for entry in entries:
                if not include_hidden and _is_hidden(entry):
                    continue
                try:
                    return_path = (
                        translate_path_from_docker(entry.path)
                        if host_root and entry.path.startswith(host_root)
                        else entry.path
                    )
                    info = FolderInfo(name=entry.name, path=return_path, is_directory=entry.is_dir())
                    if entry.is_dir():
                        try:
                            with os.scandir(entry.path) as sub:
                                info.file_count = sum(1 for e in sub if e.is_file())
                        except (OSError, PermissionError):
                            info.file_count = 0
                    else:
                        try:
                            info.size = entry.stat().st_size
                        except (OSError, PermissionError):
                            info.size = 0
                    folders.append(info)
                except (OSError, PermissionError):
                    try:
                        return_path = (
                            translate_path_from_docker(entry.path)
                            if host_root and entry.path.startswith(host_root)
                            else entry.path
                        )
                        folders.append(FolderInfo(
                            name=entry.name + " (sin acceso)",
                            path=return_path,
                            is_directory=entry.is_dir(),
                        ))
                    except Exception:
                        continue
    except (OSError, PermissionError) as e:
        raise HTTPException(403, detail=f"No se puede acceder a la ruta: {e}")

    folders.sort(key=lambda x: (not x.is_directory, x.name.lower()))
    return folders


# ---------------------------------------------------------------------------
# Validate & debug
# ---------------------------------------------------------------------------

@router.get("/validate-path")
def validate_scan_path(path: str = Query(...)) -> dict:
    normalized = os.path.realpath(path)
    resolved = resolve_path_for_docker(normalized)

    if is_blocked_path(resolved):
        return {"valid": False, "reason": "Ruta del sistema bloqueada", "suggestion": "Selecciona carpetas de usuario"}

    if not os.path.exists(resolved):
        return {"valid": False, "reason": "La ruta no existe", "suggestion": "Verifica que la ruta sea correcta"}

    if not os.path.isdir(resolved):
        return {"valid": False, "reason": "La ruta debe ser un directorio", "suggestion": "Selecciona una carpeta"}

    try:
        os.listdir(resolved)
    except PermissionError:
        return {"valid": False, "reason": "Sin permisos de lectura", "suggestion": "Selecciona otra carpeta"}

    writable = False
    try:
        test = os.path.join(resolved, ".access_test")
        with open(test, "w") as f:
            f.write("test")
        os.remove(test)
        writable = True
    except Exception:
        pass

    # FIX: Estimar archivos con límite de tiempo para no bloquear el endpoint
    file_count = 0
    import time
    deadline = time.time() + 5.0  # máximo 5 segundos
    try:
        for root, dirs, files in os.walk(resolved):
            if time.time() > deadline:
                break
            file_count += len(files)
            if file_count > 100_000:
                break
    except Exception:
        pass

    return {
        "valid": True,
        "estimated_files": file_count,
        "readable": True,
        "writable": writable,
        "message": "Ruta válida para escaneo" if writable else "Ruta de solo lectura",
        "warning": None if writable else "Algunas funciones pueden estar limitadas",
    }


@router.get("/debug/current-dir")
def get_current_dir() -> dict:
    return {
        "current_dir": os.getcwd(),
        "host_root": os.getenv("HOST_ROOT"),
        "platform": platform.system(),
    }