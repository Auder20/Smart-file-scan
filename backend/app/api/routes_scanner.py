from __future__ import annotations

import uuid
import logging
from datetime import datetime
from threading import Thread

from fastapi import APIRouter, HTTPException

from app.models.file_info import ScanRequest, ScanResult, ScanStatus, ScanProgress
from app.core.scanner import collect_all_files

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["scanner"])

# Estado en memoria — un solo usuario, un dict es suficiente
_scan_results:  dict[str, ScanResult]   = {}
_scan_progress: dict[str, ScanProgress] = {}


@router.post("", status_code=202)
def start_scan(request: ScanRequest) -> dict:
    scan_id = str(uuid.uuid4())[:8]

    _scan_progress[scan_id] = ScanProgress(
        scan_id     = scan_id,
        status      = ScanStatus.PENDING,
        progress    = 0,
        files_found = 0,
        message     = "Iniciando escaneo...",
    )

    thread = Thread(
        target = _run_scan,
        args   = (scan_id, request),
        daemon = True,
    )
    thread.start()

    return {
        "scan_id": scan_id,
        "status":  "accepted",
    }


@router.get("/{scan_id}/progress")
def get_progress(scan_id: str) -> ScanProgress:
    progress = _scan_progress.get(scan_id)
    if not progress:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return progress


@router.get("/{scan_id}")
def get_result(scan_id: str) -> ScanResult:
    result = _scan_results.get(scan_id)
    if not result:
        progress = _scan_progress.get(scan_id)
        if progress:
            raise HTTPException(409, detail=f"Scan en progreso ({progress.progress}%)")
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return result


@router.get("")
def list_scans() -> list[dict]:
    return [
        {
            "scan_id":     sid,
            "status":      p.status,
            "files_found": p.files_found,
        }
        for sid, p in _scan_progress.items()
    ]


def _run_scan(scan_id: str, request: ScanRequest) -> None:
    progress        = _scan_progress[scan_id]
    progress.status = ScanStatus.RUNNING
    progress.message = "Escaneando..."

    try:
        files, duration = collect_all_files(request)

        _scan_results[scan_id] = ScanResult(
            scan_id      = scan_id,
            root_path    = request.path,
            status       = ScanStatus.COMPLETED,
            total_files  = len(files),
            total_size   = sum(f.size for f in files),
            files        = files,
            scanned_at   = datetime.now(),
            duration_sec = duration,
        )

        progress.status      = ScanStatus.COMPLETED
        progress.progress    = 100
        progress.files_found = len(files)
        progress.message     = f"Completado: {len(files):,} archivos"

    except Exception as e:
        logger.error("Error en scan %s: %s", scan_id, e, exc_info=True)
        progress.status  = ScanStatus.FAILED
        progress.message = str(e)