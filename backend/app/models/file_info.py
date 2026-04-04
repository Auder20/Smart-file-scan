from __future__ import annotations

import os
from pydantic import BaseModel, Field, validator as field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class FileCategory(str, Enum):
    DOCUMENT   = "document"
    IMAGE      = "image"
    VIDEO      = "video"
    AUDIO      = "audio"
    CODE       = "code"
    ARCHIVE    = "archive"
    EXECUTABLE = "executable"
    OTHER      = "other"


class FileInfo(BaseModel):
    path:      str
    name:      str
    size:      int        = Field(..., ge=0)
    extension: str
    category:  FileCategory
    modified:  datetime
    created:   datetime
    hash:      Optional[str] = None

    @field_validator("extension", pre=True)
    @classmethod
    def normalize_extension(cls, v: str) -> str:
        return v.lower().lstrip(".")


class ScanRequest(BaseModel):
    path:           str
    max_depth:      int       = Field(default=20, ge=1, le=50)
    include_hidden: bool      = False
    exclude_dirs:   list[str] = Field(default_factory=lambda: [
        ".git", "node_modules", "__pycache__", ".venv"
    ])

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        # NO validar existencia aquí. Este validator corre al deserializar
        # el JSON del request, ANTES de que el scanner resuelva la ruta con
        # normalize_scan_path(). Si validamos existencia aquí:
        #   - En modo Docker: la ruta nativa del host (C:\Users) no existe
        #     dentro del contenedor → siempre falla aunque sea válida.
        #   - En modo local en Windows: backslashes pueden causar falsos negativos.
        # La validación real ocurre en scan_directory() y resolve_and_validate().
        if not v or not v.strip():
            raise ValueError("La ruta no puede estar vacía")
        return v.strip()


class ScanStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class ScanResult(BaseModel):
    scan_id:         str
    root_path:       str
    status:          ScanStatus
    total_files:     int
    total_size:      int
    files:           list[FileInfo]
    scanned_at:      datetime = Field(default_factory=datetime.now)
    duration_sec:    float    = 0.0
    files_truncated: bool     = False


class ScanProgress(BaseModel):
    scan_id:     str
    status:      ScanStatus
    progress:    int  = Field(ge=0, le=100)
    files_found: int  = 0
    message:     str  = ""


class DuplicateGroup(BaseModel):
    hash:        str
    file_count:  int
    total_size:  int
    wasted_size: int
    original:    FileInfo
    duplicates:  list[FileInfo]