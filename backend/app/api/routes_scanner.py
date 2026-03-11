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


@router.get("/all")
def list_all_scans() -> list[dict]:
    """Retorna todos los escaneos con información completa incluyendo resultados"""
    all_scans = []
    
    # Escaneos en progreso
    for sid, progress in _scan_progress.items():
        scan_info = {
            "scan_id": sid,
            "status": progress.status,
            "files_found": progress.files_found,
            "progress": progress.progress,
            "message": progress.message,
            "root_path": None,
            "total_files": 0,
            "total_size": 0,
            "scanned_at": None,
            "duration_sec": 0.0
        }
        
        # Si está completado, agregar información del resultado
        if progress.status == ScanStatus.COMPLETED and sid in _scan_results:
            result = _scan_results[sid]
            scan_info.update({
                "root_path": result.root_path,
                "total_files": result.total_files,
                "total_size": result.total_size,
                "scanned_at": result.scanned_at.isoformat(),
                "duration_sec": result.duration_sec
            })
        
        all_scans.append(scan_info)
    
    return sorted(all_scans, key=lambda x: x.get("scanned_at", ""), reverse=True)


@router.delete("/{scan_id}")
def delete_scan(scan_id: str) -> dict:
    """Elimina un escaneo completado"""
    if scan_id in _scan_results:
        del _scan_results[scan_id]
    
    if scan_id in _scan_progress:
        del _scan_progress[scan_id]
    
    return {"message": f"Scan {scan_id} eliminado correctamente"}


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