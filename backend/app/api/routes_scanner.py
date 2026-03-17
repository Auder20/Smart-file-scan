from __future__ import annotations

import uuid
import logging
from datetime import datetime
from threading import Thread, Event
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.models.file_info import ScanRequest, ScanResult, ScanStatus, ScanProgress
from app.core.scanner import scan_directory
from app.models.file_info import FileInfo
# FIX: get_files_paginated se usaba sin importar — corregido aquí
from app.db.database import (
    save_scan_metadata,
    save_file_batch,
    get_scan,
    get_files_paginated,
)
from app.core.scan_store import scan_store
from app.core.path_utils import resolve_and_validate, normalize_scan_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["scanner"])

_active_connections: list[WebSocket] = []
_event_loop: asyncio.AbstractEventLoop = None
_scan_cancel_events: dict[str, Event] = {}


def _notify_ws(data: dict) -> None:
    if not _event_loop:
        return
    message = json.dumps(data)
    for ws in _active_connections[:]:
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(message), _event_loop)
        except Exception as e:
            logger.debug(f"WS send failed, removing dead connection: {e}")
            if ws in _active_connections:
                _active_connections.remove(ws)


@router.get("/validate-path")
def validate_scan_path(path: str) -> dict:
    resolved, error = resolve_and_validate(path)
    if error:
        return {"valid": False, "reason": error, "resolved_path": resolved}
    
    estimated = _estimate_file_count(resolved) if resolved else 0
    return {"valid": True, "resolved_path": resolved, "estimated_files": estimated}


@router.post("", status_code=202)
def start_scan(request: ScanRequest) -> dict:
    scan_id = str(uuid.uuid4())[:8]
    logger.info(f"[SCAN START] scan_id={scan_id} path={request.path!r}")
    scan_store.set_scan_progress(scan_id, ScanProgress(
        scan_id=scan_id, status=ScanStatus.PENDING,
        progress=0, files_found=0, message="Iniciando escaneo...",
    ))
    t = Thread(target=_run_scan, args=(scan_id, request), daemon=True)
    t.start()
    logger.info(f"[THREAD LAUNCHED] scan_id={scan_id} alive={t.is_alive()}")
    return {"scan_id": scan_id, "status": "accepted"}


@router.get("")
def list_scans() -> list[dict]:
    all_progress = scan_store.get_all_scan_progress()
    return [
        {"scan_id": sid, "status": p.status, "files_found": p.files_found}
        for sid, p in all_progress.items()
    ]


@router.get("/all")
def list_all_scans() -> list[dict]:
    return scan_store.get_all_scans_info()


@router.get("/{scan_id}/progress")
def get_progress(scan_id: str) -> ScanProgress:
    p = scan_store.get_scan_progress(scan_id)
    if not p:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return p


@router.websocket("/ws/scan/{scan_id}")
async def scan_progress_ws(websocket: WebSocket, scan_id: str):
    await websocket.accept()
    _active_connections.append(websocket)
    logger.info(f"[WS CONNECT] scan_id={scan_id} total_connections={len(_active_connections)}")
    try:
        while True:
            progress = scan_store.get_scan_progress(scan_id)
            if progress:
                msg = {
                    "type": "progress",
                    "scan_id": scan_id,
                    "progress": progress.progress,
                    "files_found": progress.files_found,
                    "message": progress.message,
                    "current_dir": getattr(progress, "current_dir", ""),
                    "parallel_workers": getattr(progress, "parallel_workers", 0),
                    "timestamp": datetime.now().isoformat(),
                }
                if progress.status == ScanStatus.COMPLETED:
                    msg["type"] = "completed"
                    msg["progress"] = 100
                elif progress.status == ScanStatus.FAILED:
                    msg["type"] = "error"

                await websocket.send_text(json.dumps(msg))

                if progress.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                    await asyncio.sleep(1)
                    break
            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for scan {scan_id}")
    except Exception as e:
        logger.error(f"WebSocket error for scan {scan_id}: {e}")
    finally:
        if websocket in _active_connections:
            _active_connections.remove(websocket)


@router.get("/{scan_id}/files")
def get_scan_files(scan_id: str, page: int = 1, page_size: int = 1000) -> dict:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        p = scan_store.get_scan_progress(scan_id)
        if p:
            raise HTTPException(409, detail=f"Scan en progreso ({p.progress}%)")
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    if not result.files_truncated:
        return {
            "scan_id": scan_id,
            "files": [f.dict() for f in result.files],
            "total_files": len(result.files),
            "page": 1,
            "page_size": len(result.files),
            "total_pages": 1,
            "files_truncated": False,
        }

    # FIX: get_files_paginated ahora está correctamente importado
    logger.info(f"Loading files from SQLite for truncated scan {scan_id}, page {page}")
    try:
        paginated = get_files_paginated(scan_id, page, page_size)
        return {
            "scan_id": scan_id,
            "files": [f.dict() for f in paginated["files"]],
            "total_files": paginated["total_files"],
            "page": page,
            "page_size": page_size,
            "total_pages": paginated["total_pages"],
            "files_truncated": True,
        }
    except Exception as e:
        logger.error(f"Error loading files from SQLite: {e}")
        raise HTTPException(500, detail=f"Error cargando archivos: {e}")


@router.get("/{scan_id}")
def get_result(scan_id: str) -> ScanResult:
    result = scan_store.get_scan_result(scan_id)
    if not result:
        p = scan_store.get_scan_progress(scan_id)
        if p:
            raise HTTPException(409, detail=f"Scan en progreso ({p.progress}%)")
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
    return result


@router.delete("/{scan_id}")
def delete_scan(scan_id: str) -> dict:
    if scan_id in _scan_cancel_events:
        _scan_cancel_events[scan_id].set()
        del _scan_cancel_events[scan_id]
    scan_store.remove_scan(scan_id)
    # También eliminar de SQLite para que no reaparezca al reiniciar
    try:
        from app.db.database import delete_scan_data
        delete_scan_data(scan_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error borrando scan {scan_id} de SQLite: {e}")
    return {"message": f"Scan {scan_id} eliminado correctamente"}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_scan(scan_id: str, request: ScanRequest) -> None:
    import time

    try:
        cancel_event = Event()
        _scan_cancel_events[scan_id] = cancel_event

        progress = scan_store.get_scan_progress(scan_id)
        if not progress:
            logger.error(f"[SCAN ABORT] scan_id={scan_id} not found in progress store")
            return

        # Reemplazar objeto para evitar problemas de mutación con Pydantic v2
        new_progress = ScanProgress(
            scan_id=scan_id, status=ScanStatus.RUNNING,
            progress=0, files_found=0, message="Escaneando...",
        )
        scan_store.set_scan_progress(scan_id, new_progress)
        progress = new_progress

        files: list[FileInfo] = []
        start = time.time()
        logger.info(f"[SCAN RUNNING] scan_id={scan_id} path={request.path!r}")

    except Exception as e:
        logger.error(f"[SCAN INIT ERROR] scan_id={scan_id} {type(e).__name__}: {e}", exc_info=True)
        _notify_ws({"type": "error", "scan_id": scan_id,
                    "message": f"Error iniciando scan: {e}",
                    "timestamp": datetime.now().isoformat()})
        return

    try:
        save_scan_metadata(scan_id, request.path, ScanStatus.RUNNING.value)
    except Exception as e:
        logger.error(f"Failed to save scan metadata: {e}")

    try:
        resolved_estimating_path = normalize_scan_path(request.path)
        estimated = _estimate_file_count(resolved_estimating_path)

        for event in scan_directory(request):
            if cancel_event.is_set():
                logger.info(f"Scan {scan_id} cancelled")
                scan_store.set_scan_progress(scan_id, ScanProgress(
                    scan_id=scan_id, status=ScanStatus.FAILED,
                    progress=0, files_found=len(files),
                    message="Escaneo cancelado por el usuario",
                ))
                try:
                    save_scan_metadata(scan_id, request.path, ScanStatus.FAILED.value)
                except Exception:
                    pass
                _notify_ws({"type": "error", "scan_id": scan_id,
                            "message": progress.message,
                            "timestamp": datetime.now().isoformat()})
                return

            if isinstance(event, FileInfo):
                files.append(event)
                count = len(files)
                if count % 500 == 0:
                    try:
                        save_file_batch(scan_id, files[-500:])
                    except Exception as e:
                        logger.error(f"Failed to save file batch: {e}")
            elif isinstance(event, dict):
                etype = event.get("type")
                if etype in ("error", "timeout"):
                    err_msg = event.get("message", f"Escaneo falló ({etype})")
                    logger.error(f"Scan {scan_id} ended with {etype}: {err_msg}")
                    scan_store.set_scan_progress(scan_id, ScanProgress(
                        scan_id=scan_id, status=ScanStatus.FAILED,
                        progress=0, files_found=len(files), message=err_msg,
                    ))
                    progress = scan_store.get_scan_progress(scan_id)
                    try:
                        save_scan_metadata(scan_id, request.path, ScanStatus.FAILED.value)
                    except Exception:
                        pass
                    _notify_ws({"type": "error", "scan_id": scan_id, 
                                "message": progress.message, "timestamp": datetime.now().isoformat()})
                    return
                elif etype == "progress":
                    count = event.get("count", len(files))
                    pct = min(int(count * 100 / estimated), 99) if estimated > 0 else 0
                    msg = f"Escaneando… {count:,} archivos encontrados"
                    # Reemplazar objeto completo (compatible con Pydantic v2 frozen)
                    scan_store.set_scan_progress(scan_id, ScanProgress(
                        scan_id=scan_id, status=ScanStatus.RUNNING,
                        progress=pct, files_found=count, message=msg,
                    ))
                    progress = scan_store.get_scan_progress(scan_id)

                    _notify_ws({
                        "type": "progress", "scan_id": scan_id,
                        "progress": progress.progress, "files_found": count,
                        "message": progress.message,
                        "current_dir": event.get("current_dir", ""),
                        "parallel_workers": 0,
                        "timestamp": datetime.now().isoformat(),
                    })

        # Guardar archivos restantes
        last_saved = (len(files) // 500) * 500
        remaining = files[last_saved:]
        if remaining:
            try:
                save_file_batch(scan_id, remaining)
            except Exception as e:
                logger.error(f"Failed to save final batch: {e}")

        duration = round(time.time() - start, 2)
        total_size = sum(f.size for f in files)

        try:
            save_scan_metadata(
                scan_id, request.path, ScanStatus.COMPLETED.value,
                len(files), total_size, datetime.now(), duration,
            )
        except Exception as e:
            logger.error(f"Failed to update scan metadata: {e}")

        scan_store.set_scan_result(scan_id, ScanResult(
            scan_id=scan_id, root_path=request.path,
            status=ScanStatus.COMPLETED,
            total_files=len(files), total_size=total_size,
            files=files[:1000],
            scanned_at=datetime.now(), duration_sec=duration,
            files_truncated=len(files) > 1000,
        ))

        scan_store.set_scan_progress(scan_id, ScanProgress(
            scan_id=scan_id, status=ScanStatus.COMPLETED,
            progress=100, files_found=len(files),
            message=f"Completado: {len(files):,} archivos en {duration}s",
        ))
        progress = scan_store.get_scan_progress(scan_id)
        logger.info(f"[SCAN DONE] scan_id={scan_id} files={len(files)} duration={duration}s")

        _notify_ws({
            "type": "completed", "scan_id": scan_id, "progress": 100,
            "files_found": len(files), "message": progress.message,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"[SCAN ERROR] scan_id={scan_id} error={type(e).__name__}: {e}", exc_info=True)
        scan_store.set_scan_progress(scan_id, ScanProgress(
            scan_id=scan_id, status=ScanStatus.FAILED,
            progress=0, files_found=len(files) if 'files' in dir() else 0,
            message=f"{type(e).__name__}: {e}",
        ))
        progress = scan_store.get_scan_progress(scan_id)
        try:
            save_scan_metadata(scan_id, request.path, ScanStatus.FAILED.value)
        except Exception:
            pass
        _notify_ws({"type": "error", "scan_id": scan_id,
                    "message": progress.message,
                    "timestamp": datetime.now().isoformat()})
    finally:
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