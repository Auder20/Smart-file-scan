"""
app/core/security.py
--------------------
Validaciones de seguridad centralizadas.

Consolida en un solo lugar las comprobaciones que antes estaban
duplicadas o incompletas en routes_duplicates y routes_explorer.
"""
from __future__ import annotations

import os
import re
import logging

logger = logging.getLogger(__name__)

# Patrones que indican intentos de path traversal
_TRAVERSAL_PATTERNS = re.compile(
    r"(\.\.[/\\])"         # ../  o ..\
    r"|([/\\]\.\.[/\\]?)"  # /../ o \..\
    r"|(^\.\.)"            # empieza con ..
    r"|(%2e%2e)"           # URL-encoded ..
    r"|(%252e%252e)",      # doble URL-encoded ..
    re.IGNORECASE,
)

# Prefijos de rutas críticas del sistema que nunca deben modificarse
_SYSTEM_PREFIXES_LINUX  = ("/proc/", "/sys/", "/dev/", "/run/", "/boot/", "/etc/")
_SYSTEM_PREFIXES_WIN    = (
    "c:\\windows\\", "c:\\program files\\",
    "c:\\$recycle.bin", "c:\\system volume",
)


def validate_no_traversal(path: str) -> str:
    """
    Lanza ValueError si la ruta contiene secuencias de path traversal.
    Devuelve la ruta normalizada si es segura.

    Cubre:
      - ../  ..\
      - URL-encoded: %2e%2e
      - Doble-encoded: %252e%252e
    """
    if _TRAVERSAL_PATTERNS.search(path):
        raise ValueError(f"Path traversal detectado en ruta: {path!r}")

    # Normalizar y volver a comprobar (por si la codificación oculta el patrón)
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal detectado (post-normalization): {normalized!r}")

    return normalized


def validate_not_system_path(path: str) -> None:
    """
    Lanza ValueError si la ruta apunta a directorios del sistema
    que nunca deben ser modificados o borrados.
    """
    lower = path.lower().replace("/", os.sep)
    import platform
    prefixes = _SYSTEM_PREFIXES_WIN if platform.system() == "Windows" else _SYSTEM_PREFIXES_LINUX
    for prefix in prefixes:
        if lower.startswith(prefix.lower()):
            raise ValueError(f"Operación bloqueada sobre ruta del sistema: {path!r}")


def validate_delete_path(path: str) -> str:
    """
    Ejecuta todas las validaciones de seguridad sobre una ruta
    antes de intentar eliminar el archivo.

    Devuelve la ruta normalizada si pasa todas las comprobaciones.
    Lanza ValueError con mensaje descriptivo en caso contrario.
    """
    if not path or not path.strip():
        raise ValueError("Ruta vacía")

    # 1. Sin traversal
    normalized = validate_no_traversal(path)

    # 2. No es ruta del sistema
    validate_not_system_path(normalized)

    # 3. Debe ser ruta absoluta (las relativas son ambiguas en contexto Docker)
    if not os.path.isabs(normalized):
        # Intentar con la ruta original antes de rechazarla
        if not os.path.isabs(path):
            raise ValueError(f"Ruta relativa no permitida: {path!r}")
        normalized = path

    return normalized


def sanitize_scan_path(path: str) -> str:
    """
    Limpia y valida una ruta de escaneo.
    Más permisiva que validate_delete_path, pero igualmente segura.
    """
    if not path or not path.strip():
        raise ValueError("Ruta vacía")

    normalized = validate_no_traversal(path.strip())
    validate_not_system_path(normalized)
    return normalized