"""
core/path_utils.py
------------------
Utilidades de resolución de rutas compartidas entre módulos.

Historial de bugs corregidos:
  - v1: dependencia circular file_info → routes_explorer
  - v2: rutas nativas no se traducían al escanear en Docker
  - v3: rutas ya en formato Docker (/mnt/host/...) se duplicaban
        añadiendo /host otra vez → /host/mnt/host/...
"""
from __future__ import annotations

import os
import platform


def resolve_path_for_docker(path: str) -> str:
    """
    Traduce rutas nativas del SO a formato HOST_ROOT/X para acceso en Docker.

    Ejemplos con HOST_ROOT=/host:
        C:\\Users\\John  →  /host/c/Users/John
        /home/user      →  /host/home/user

    En modo nativo (HOST_ROOT no definido) devuelve la ruta sin cambios.
    Si la ruta ya empieza con HOST_ROOT la devuelve sin modificar.
    """
    host_root = os.getenv("HOST_ROOT", "").rstrip("/")
    if not host_root:
        return path

    # Ya tiene el prefijo correcto: no duplicar
    if path.startswith(host_root + "/") or path == host_root:
        return path

    if platform.system() == "Windows":
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].lower()
            rest = path[2:].replace("\\", "/")
            return f"{host_root}/{drive}{rest}"
    else:
        if path.startswith("/"):
            return f"{host_root}{path}"

    return path


def translate_path_from_docker(docker_path: str) -> str:
    """
    Invierte resolve_path_for_docker: HOST_ROOT/X → ruta nativa del SO.
    """
    host_root = os.getenv("HOST_ROOT", "").rstrip("/")
    if not host_root or not docker_path.startswith(host_root):
        return docker_path

    relative = docker_path[len(host_root):]

    if platform.system() == "Windows":
        if len(relative) >= 2 and relative[1] == "/":
            drive = relative[0].upper()
            rest = relative[2:].replace("/", "\\")
            return f"{drive}:\\{rest}"
    else:
        return relative

    return docker_path


def normalize_scan_path(path: str) -> str:
    """
    Resuelve una ruta de escaneo para que sea accesible dentro del contenedor.
    """
    host_root = os.getenv("HOST_ROOT", "").rstrip("/")

    # Modo nativo: sin Docker, devolver normalizado
    if not host_root:
        return os.path.normpath(path)

    # Ya tiene prefijo Docker correcto → no tocar
    if path.startswith(host_root + "/") or path == host_root:
        return path

    # En Docker: traducir siempre primero, luego verificar existencia
    translated = resolve_path_for_docker(path)
    if os.path.exists(translated):
        return translated

    # Último recurso: devolver traducido aunque no exista
    # (el scanner reportará el error con la ruta correcta)
    return translated


def is_blocked_path(path: str) -> bool:
    """
    Comprueba si una ruta apunta a directorios del sistema que no
    deben ser escaneados ni modificados.
    """
    normalized = os.path.normpath(path).lower()

    if platform.system() == "Windows":
        blocked = [
            "c:\\windows\\system32",
            "c:\\windows\\syswow64",
            "c:\\$recycle.bin",
            "c:\\system volume information",
        ]
    elif platform.system() == "Linux":
        blocked = ["/proc", "/sys", "/dev", "/run"]
    else:
        blocked = ["/system", "/private/var/vm", "/dev"]

    return any(normalized.startswith(b.lower()) for b in blocked)


def resolve_and_validate(path: str) -> tuple[str, str | None]:
    """
    Normaliza la ruta y verifica que exista y sea un directorio.

    Devuelve (ruta_resuelta, None) si es válida,
    o ("", mensaje_de_error) si falla alguna comprobación.
    """
    resolved = normalize_scan_path(path)

    if is_blocked_path(resolved):
        return "", "Ruta del sistema bloqueada por seguridad"

    if not os.path.exists(resolved):
        return "", f"La ruta '{path}' no existe"

    if not os.path.isdir(resolved):
        return "", "La ruta debe ser un directorio"

    return resolved, None