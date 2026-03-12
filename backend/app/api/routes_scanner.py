from __future__ import annotations

import uuid
import logging
from datetime import datetime
from threading import Thread, Event
import asyncio
import json
import websockets

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.models.file_info import ScanRequest, ScanResult, ScanStatus, ScanProgress
from app.core.scanner import scan_directory
from app.models.file_info import FileInfo
from app.db.database import save_scan_metadata, save_file_batch, get_scan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["scanner"])

# WebSocket connections for real-time progress
_active_connections: list[WebSocket] = []

_scan_results:  dict[str, ScanResult]   = {}
_scan_progress: dict[str, ScanProgress] = {}

# Global event loop reference for WebSocket communication from threads
_event_loop: asyncio.AbstractEventLoop = None

# Global cancel events for scans
_scan_cancel_events: dict[str, Event] = {}

def _notify_ws(data: dict) -> None:
    """Send data to all active WebSocket connections safely from any thread."""
    if not _event_loop:
        logger.warning("Event loop not available for WebSocket notification")
        return
    
    message = json.dumps(data)
    # Use a copy to avoid modification during iteration
    for ws in _active_connections[:]:
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(message), _event_loop)
        except Exception as e:
            logger.debug(f"Failed to send WebSocket message: {e}")


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
    await websocket.accept()
    _active_connections.append(websocket)
    try:
        while True:
            progress = _scan_progress.get(scan_id)
            if progress:
                msg = {
                    "type": "progress",
                    "scan_id": scan_id,
                    "progress": progress.progress,
                    "files_found": progress.files_found,
                    "message": progress.message,
                    "current_dir": getattr(progress, 'current_dir', ''),
                    "parallel_workers": getattr(progress, 'parallel_workers', 0),
                    "timestamp": datetime.now().isoformat()
                }
                # Override type for terminal states
                if progress.status == ScanStatus.COMPLETED:
                    msg["type"] = "completed"
                    msg["progress"] = 100
                elif progress.status == ScanStatus.FAILED:
                    msg["type"] = "error"

                await websocket.send_text(json.dumps(msg))

                if progress.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                    await asyncio.sleep(1)   # give frontend time to process
                    break
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for scan {scan_id}")
    except Exception as e:
        logger.error(f"WebSocket error for scan {scan_id}: {e}")
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
    # Cancel the scan if it's running
    if scan_id in _scan_cancel_events:
        _scan_cancel_events[scan_id].set()
        del _scan_cancel_events[scan_id]
    
    _scan_results.pop(scan_id, None)
    _scan_progress.pop(scan_id, None)
    return {"message": f"Scan {scan_id} eliminado correctamente"}


# ── Background worker ──────────────────────────────────────────────────────────

def _run_scan(scan_id: str, request: ScanRequest) -> None:
    import time

    # Create cancel event for this scan
    cancel_event = Event()
    _scan_cancel_events[scan_id] = cancel_event

    progress         = _scan_progress[scan_id]
    progress.status  = ScanStatus.RUNNING
    progress.message = "Escaneando..."
    files: list[FileInfo] = []
    start = time.time()
    
    # Save initial scan metadata
    try:
        save_scan_metadata(scan_id, request.path, ScanStatus.RUNNING.value)
    except Exception as e:
        logger.error(f"Failed to save scan metadata: {e}")
    
    try:
        # Estimate file count before scanning
        estimated = _estimate_file_count(request.path)
        
        for event in scan_directory(request):
            # Check if scan was cancelled
            if cancel_event.is_set():
                logger.info(f"Scan {scan_id} cancelled by user")
                progress.status = ScanStatus.FAILED
                progress.message = "Escaneo cancelado por el usuario"
                try:
                    save_scan_metadata(scan_id, request.path, ScanStatus.FAILED.value)
                except:
                    pass
                _notify_ws({
                    "type": "error",
                    "scan_id": scan_id,
                    "message": progress.message,
                    "timestamp": datetime.now().isoformat()
                })
                return

            if isinstance(event, FileInfo):
                files.append(event)
                count            = len(files)
                progress.files_found = count
                progress.message = f"Escaneando… {count:,} archivos encontrados"
                if estimated > 0:
                    progress.progress = min(int(count * 100 / estimated), 99)
                
                # Save batch to SQLite every 500 files
                if count % 500 == 0:
                    try:
                        save_file_batch(scan_id, files[-500:])  # Save last 500 files
                        logger.debug(f"Saved batch of 500 files to database for scan {scan_id}")
                    except Exception as e:
                        logger.error(f"Failed to save file batch: {e}")
                
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
                
                _notify_ws(update_data)
        
        # Save remaining files
        remaining_files = files[len(files) - (len(files) % 500):] if len(files) % 500 != 0 else []
        if remaining_files:
            try:
                save_file_batch(scan_id, remaining_files)
                logger.debug(f"Saved final batch of {len(remaining_files)} files to database for scan {scan_id}")
            except Exception as e:
                logger.error(f"Failed to save final file batch: {e}")
        
        duration = round(time.time() - start, 2)
        total_size = sum(f.size for f in files)
        
        # Update scan metadata with completion data
        try:
            save_scan_metadata(
                scan_id, request.path, ScanStatus.COMPLETED.value,
                len(files), total_size, datetime.now(), duration
            )
        except Exception as e:
            logger.error(f"Failed to update scan metadata: {e}")
        
        # Keep light reference in memory for compatibility
        _scan_results[scan_id] = ScanResult(
            scan_id      = scan_id,
            root_path    = request.path,
            status       = ScanStatus.COMPLETED,
            total_files  = len(files),
            total_size   = total_size,
            files        = files[:1000],  # Keep only first 1000 files in memory
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
        
        _notify_ws(final_update)
                
    except Exception as e:
        logger.error("Error en scan %s: %s", scan_id, e, exc_info=True)
        progress.status  = ScanStatus.FAILED
        progress.message = str(e)
        
        # Update scan metadata with error status
        try:
            save_scan_metadata(scan_id, request.path, ScanStatus.FAILED.value)
        except:
            pass
        
        # Enviar error por WebSocket
        error_update = {
            "type": "error",
            "scan_id": scan_id,
            "message": progress.message,
            "timestamp": datetime.now().isoformat()
        }
        
        _notify_ws(error_update)
    finally:
        # Clean up cancel event
        _scan_cancel_events.pop(scan_id, None)


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