import logging
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_scanner    import router as scanner_router
from app.api.routes_duplicates import router as duplicates_router
from app.api.routes_stats      import router as stats_router
from app.api.routes_files      import router as files_router
from app.api.routes_explorer   import router as explorer_router

# PRIORIDAD 6: nivel de log configurable desde variable de entorno
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend iniciado — LOG_LEVEL=%s", _log_level)
    logger.info("Documentación en http://localhost:8000/docs")

    # Pasar el event loop al módulo de scanner para notificaciones WebSocket
    import app.api.routes_scanner as scanner_mod
    scanner_mod._event_loop = asyncio.get_running_loop()

    # Rehidratar escaneos completados desde SQLite al reiniciar
    await _rehydrate_scanner_state()

    yield

    # PRIORIDAD 6: cerrar conexiones SQLite thread-local al apagar
    logger.info("Cerrando conexiones de base de datos...")
    try:
        from app.db.database import close_connection
        close_connection()
    except Exception as e:
        logger.warning(f"Error cerrando conexión DB: {e}")

    logger.info("Backend cerrado correctamente")


async def _rehydrate_scanner_state() -> None:
    """Carga escaneos completados de SQLite en memoria al arrancar."""
    try:
        from app.db.database import get_scans, get_files_paginated
        from app.models.file_info import ScanProgress, ScanStatus, ScanResult
        from app.core.scan_store import scan_store
        from datetime import datetime

        logger.info("Rehidratando estado del scanner desde SQLite...")
        try:
            scans = get_scans()
        except Exception as e:
            logger.warning(f"Base de datos no disponible durante rehidratación: {e}")
            return

        count = 0
        for scan_data in scans:
            if scan_data.get("status") != "completed":
                continue

            scan_id = scan_data["scan_id"]

            scan_store.set_scan_progress(scan_id, ScanProgress(
                scan_id=scan_id, status=ScanStatus.COMPLETED, progress=100,
                files_found=scan_data.get("total_files", 0),
                message=f"Completado: {scan_data.get('total_files', 0):,} archivos",
            ))

            try:
                paginated = get_files_paginated(scan_id, 1, 1)
                total_files = paginated.get("total_files", 0)
            except Exception:
                total_files = scan_data.get("total_files", 0)

            scanned_at_raw = scan_data.get("scanned_at")
            try:
                scanned_at = datetime.fromisoformat(scanned_at_raw) if scanned_at_raw else datetime.now()
            except (ValueError, TypeError):
                scanned_at = datetime.now()

            scan_store.set_scan_result(scan_id, ScanResult(
                scan_id=scan_id,
                root_path=scan_data.get("root_path", ""),
                status=ScanStatus.COMPLETED,
                total_files=total_files,
                total_size=scan_data.get("total_size", 0),
                files=[],           # vacío — se carga desde DB bajo demanda
                scanned_at=scanned_at,
                duration_sec=scan_data.get("duration_sec", 0.0),
                files_truncated=True,
            ))
            count += 1

        logger.info(f"Rehidratados {count} escaneos completados desde la base de datos")

    except Exception as e:
        logger.error(f"Error durante rehidratación: {e}", exc_info=True)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart File Organizer API",
    version="1.0.0",
    lifespan=lifespan,
)


def _get_cors_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(scanner_router)
app.include_router(duplicates_router)
app.include_router(stats_router)
app.include_router(files_router)
app.include_router(explorer_router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["system"])
def root():
    return {"docs": "http://localhost:8000/docs"}