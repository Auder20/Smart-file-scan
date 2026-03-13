import logging
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_scanner    import router as scanner_router
from app.api.routes_duplicates import router as duplicates_router
from app.api.routes_stats      import router as stats_router
from app.api.routes_files     import router as files_router
from app.api.routes_explorer  import router as explorer_router

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt= "%H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend iniciado")
    logger.info("Documentación en http://localhost:8000/docs")
    
    # Pass event loop to scanner module for WebSocket communication
    import app.api.routes_scanner as scanner_mod
    scanner_mod._event_loop = asyncio.get_running_loop()
    
    # ARCH 1: Rehydrate completed scans from SQLite
    await _rehydrate_scanner_state()
    
    yield
    logger.info("Backend cerrado")


async def _rehydrate_scanner_state():
    """Load completed scans from SQLite into memory on startup"""
    try:
        from app.db.database import get_scans, get_files_paginated
        from app.models.file_info import ScanProgress, ScanStatus, ScanResult
        from app.core.scan_store import scan_store
        from datetime import datetime
        
        logger.info("Rehydrating scanner state from SQLite...")
        
        # Get all scans from database
        try:
            scans = get_scans()
        except Exception as e:
            logger.warning(f"Database not available during rehydration: {e}")
            scans = []
        
        rehydrated_count = 0
        
        for scan_data in scans:
            scan_id = scan_data["scan_id"]
            status = scan_data["status"]
            
            # Only rehydrate completed scans
            if status == "completed":
                # Create basic progress entry
                progress = ScanProgress(
                    scan_id=scan_id,
                    status=ScanStatus.COMPLETED,
                    progress=100,
                    files_found=scan_data.get("total_files", 0),
                    message=f"Completado: {scan_data.get('total_files', 0):,} archivos"
                )
                
                # Store in scan_store
                scan_store.set_scan_progress(scan_id, progress)
                
                # Create minimal ScanResult for rehydration (files loaded from DB on demand)
                try:
                    # Get total files count from database
                    paginated_result = get_files_paginated(scan_id, 1, 1)  # Just get count
                    total_files = paginated_result.get('total_files', 0)
                except Exception:
                    total_files = scan_data.get("total_files", 0)
                
                result = ScanResult(
                    scan_id=scan_id,
                    root_path=scan_data.get("root_path", ""),
                    status=ScanStatus.COMPLETED,
                    total_files=total_files,
                    total_size=scan_data.get("total_size", 0),
                    files=[],  # Empty - will be loaded from DB on demand
                    scanned_at=datetime.fromisoformat(scan_data["scanned_at"]) if scan_data.get("scanned_at") else datetime.now(),
                    duration_sec=scan_data.get("duration_sec", 0.0),
                    files_truncated=True  # Always true for rehydrated scans
                )
                
                scan_store.set_scan_result(scan_id, result)
                rehydrated_count += 1
                
                logger.debug(f"Rehydrated scan {scan_id} with {total_files} files")
        
        logger.info(f"Rehydrated {rehydrated_count} completed scans from database")
        
    except Exception as e:
        logger.error(f"Failed to rehydrate scanner state: {e}")
        # Continue startup even if rehydration fails


app = FastAPI(
    title    = "Smart File Organizer API",
    version  = "1.0.0",
    lifespan = lifespan,
)

# SEC 2: Configure CORS from environment variable
def _get_cors_origins() -> list[str]:
    """Get CORS origins from environment variable or use defaults"""
    allowed_origins = os.getenv("ALLOWED_ORIGINS")
    if allowed_origins:
        # Split comma-separated origins and strip whitespace
        return [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]
    # Default origins for development
    return ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins  = _get_cors_origins(),  # SEC 2: Use configurable origins
    allow_methods  = ["GET", "POST", "PUT", "DELETE"],
    allow_headers  = ["Content-Type", "Authorization"],
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