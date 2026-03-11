import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_scanner    import router as scanner_router
from app.api.routes_duplicates import router as duplicates_router
from app.api.routes_stats      import router as stats_router

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
    yield
    logger.info("Backend cerrado")


app = FastAPI(
    title    = "Smart File Organizer API",
    version  = "1.0.0",
    lifespan = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

app.include_router(scanner_router)
app.include_router(duplicates_router)
app.include_router(stats_router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["system"])
def root():
    return {"docs": "http://localhost:8000/docs"}