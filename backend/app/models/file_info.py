from __future__ import annotations

import os

from pydantic import BaseModel, Field, field_validator
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

    @field_validator("extension", mode="before")
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
    def path_must_exist(cls, v: str) -> str:
        # FIX: usar normalize_scan_path en vez de _resolve_path_for_docker
        # para que funcione tanto con rutas nativas (D:\...) como con rutas
        # ya en formato Docker (/host/d/...) que llegan del explorador.
        from app.core.path_utils import normalize_scan_path
        resolved = normalize_scan_path(v)
        if not os.path.isdir(resolved):
            raise ValueError(f"El directorio no existe: {resolved} (ruta original: {v})")
        return v


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