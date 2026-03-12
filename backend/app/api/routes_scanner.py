from __future__ import annotations

import uuid
import logging
from datetime import datetime
from threading import Thread
import asyncio
import json
import websockets

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.models.file_info import ScanRequest, ScanResult, ScanStatus, ScanProgress
from app.core.scanner import scan_directory
from app.models.file_info import FileInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["scanner"])

# WebSocket connections for real-time progress
_active_connections: list[WebSocket] = []

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
    Thread(target=_run_scan, args=(scan_id, request), daemon=True).start()
    return {"scan_id": scan_id, "status": "accepted"}


@router.get("")
def list_scans() -> list[dict]:
    return [
        {"scan_id": sid, "status": p.status, "files_found": p.files_found}
        for sid, p in _scan_progress.items()
    ]


# ⚠️  CRITICAL: /all and /stats MUST come BEFORE /{scan_id}
# FastAPI matches routes top-to-bottom; if /{scan_id} is first,
# "all" and "stats" are treated as scan IDs → 404.

@router.get("/all")
def list_all_scans() -> list[dict]:
    """Returns all scans with full info including completed results."""
    all_scans = []

    for sid, progress in _scan_progress.items():
        scan_info: dict = {
            "scan_id":      sid,
            "status":       progress.status,
            "files_found":  progress.files_found,
            "progress":     progress.progress,
            "message":      progress.message,
            "root_path":    None,
            "total_files":  0,
            "total_size":   0,
            "scanned_at":   None,
            "duration_sec": 0.0,
        }

        if progress.status == ScanStatus.COMPLETED and sid in _scan_results:
            r = _scan_results[sid]
            scan_info.update({
                "root_path":    r.root_path,
                "total_files":  r.total_files,
                "total_size":   r.total_size,
                "scanned_at":   r.scanned_at.isoformat(),
                "duration_sec": r.duration_sec,
            })

        all_scans.append(scan_info)

    return sorted(all_scans, key=lambda x: x.get("scanned_at") or "", reverse=True)


@router.get("/{scan_id}/progress")
def get_progress(scan_id: str) -> ScanProgress:
    p = _scan_progress.get(scan_id)
    if not p:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return p


@router.websocket("/ws/scan/{scan_id}")
async def scan_progress(websocket: WebSocket, scan_id: str):
    """WebSocket para progreso en tiempo real"""
    await websocket.accept()
    _active_connections.append(websocket)
    
    try:
        while True:
            progress = _scan_progress.get(scan_id)
            if progress:
                await websocket.send_text(json.dumps({
                    "type": "progress",
                    "scan_id": scan_id,
                    "progress": progress.progress,
                    "files_found": progress.files_found,
                    "message": progress.message,
                    "current_dir": getattr(progress, 'current_dir', ''),
                    "parallel_workers": getattr(progress, 'parallel_workers', 0),
                    "timestamp": datetime.now().isoformat()
                }))
            await asyncio.sleep(0.5)  # Actualizar cada 500ms
    except WebSocketDisconnect:
        logger.info(f"WebSocket desconectado para scan {scan_id}")
    finally:
        if websocket in _active_connections:
            _active_connections.remove(websocket)


@router.get("/{scan_id}")
def get_result(scan_id: str) -> ScanResult:
    result = _scan_results.get(scan_id)
    if not result:
        p = _scan_progress.get(scan_id)
        if p:
            raise HTTPException(409, detail=f"Scan en progreso ({p.progress}%)")
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return result


@router.delete("/{scan_id}")
def delete_scan(scan_id: str) -> dict:
    _scan_results.pop(scan_id, None)
    _scan_progress.pop(scan_id, None)
    return {"message": f"Scan {scan_id} eliminado correctamente"}


# ── Background worker ──────────────────────────────────────────────────────────

def _run_scan(scan_id: str, request: ScanRequest) -> None:
    import time

    progress         = _scan_progress[scan_id]
    progress.status  = ScanStatus.RUNNING
    progress.message = "Escaneando..."
    files: list[FileInfo] = []
    start = time.time()
    
    try:
        estimated = _estimate_file_count(request.path)
        for event in scan_directory(request):
            if isinstance(event, FileInfo):
                files.append(event)
                count            = len(files)
                progress.files_found = count
                progress.message = f"Escaneando… {count:,} archivos encontrados"
                if estimated > 0:
                    progress.progress = min(int(count * 100 / estimated), 99)
                
                # Enviar actualización por WebSocket a todos los clientes conectados
                update_data = {
                    "type": "progress",
                    "scan_id": scan_id,
                    "progress": progress.progress,
                    "files_found": progress.files_found,
                    "message": progress.message,
                    "current_dir": getattr(event, 'path', '').split('/')[-1] if hasattr(event, 'path') else '',
                    "parallel_workers": getattr(progress, 'parallel_workers', 0),
                    "timestamp": datetime.now().isoformat()
                }
                
                for ws in _active_connections:
                    try:
                        asyncio.create_task(ws.send_text(json.dumps(update_data)))
                    except:
                        pass  # Ignorar errores de WebSocket desconectados
                
                if count % 100 == 0:  # Enviar cada 100 archivos
                    yield event
        
        duration = round(time.time() - start, 2)
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
        
        progress.status  = ScanStatus.COMPLETED
        progress.progress    = 100
        progress.message     = f"Completado: {len(files):,} archivos en {duration}s"
        
        # Enviar actualización final por WebSocket
        final_update = {
            "type": "completed",
            "scan_id": scan_id,
            "progress": 100,
            "files_found": len(files),
            "message": progress.message,
            "timestamp": datetime.now().isoformat()
        }
        
        for ws in _active_connections:
            try:
                asyncio.create_task(ws.send_text(json.dumps(final_update)))
            except:
                pass
                
    except Exception as e:
        logger.error("Error en scan %s: %s", scan_id, e, exc_info=True)
        progress.status  = ScanStatus.FAILED
        progress.message = str(e)
        
        # Enviar error por WebSocket
        error_update = {
            "type": "error",
            "scan_id": scan_id,
            "message": progress.message,
            "timestamp": datetime.now().isoformat()
        }
        
        for ws in _active_connections:
            try:
                asyncio.create_task(ws.send_text(json.dumps(error_update)))
            except:
                pass


def _estimate_file_count(path: str) -> int:
    import os
    count = 0
    try:
        for root, dirs, files in os.walk(path):
            depth = root.replace(path, "").count(os.sep)
            if depth >= 2:
                dirs[:] = []
                continue
            count += len(files)
            if count > 100_000:
                return count
    except Exception:
        pass
    return count