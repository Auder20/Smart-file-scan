from __future__ import annotations

import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import threading

from app.models.file_info import FileInfo, FileCategory

logger = logging.getLogger(__name__)


# ── Ruta de la base de datos ───────────────────────────────────────────────────
# FIX: en Docker Desktop con Windows el volumen ./backend:/app se monta con
# permisos restrictivos para usuarios no-root → "attempt to write a readonly
# database". Se resuelve con tres niveles de fallback:
#   1. Variable de entorno DB_PATH (máxima prioridad, para producción)
#   2. /app/smart_file_organizer.db  (workdir del contenedor, si es escribible)
#   3. /tmp/smart_file_organizer.db  (siempre escribible en cualquier contenedor)

def _resolve_db_path() -> str:
    env_path = os.getenv("DB_PATH")
    if env_path:
        return env_path

    candidates = [
        "/app/smart_file_organizer.db",
        "/tmp/smart_file_organizer.db",
    ]
    for path in candidates:
        directory = os.path.dirname(path) or "."
        try:
            test = path + ".write_test"
            with open(test, "w") as f:
                f.write("x")
            os.remove(test)
            return path
        except OSError:
            continue

    # Último recurso: directorio actual
    return "smart_file_organizer.db"


DB_PATH = _resolve_db_path()


# ── Pool de conexiones thread-local ───────────────────────────────────────────
_thread_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """
    Devuelve una conexión SQLite por hilo con WAL mode activado.
    WAL permite lecturas concurrentes mientras un escaneo escribe en lotes.
    """
    if not hasattr(_thread_local, "connection") or _thread_local.connection is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-10000")
        _thread_local.connection = conn
        logger.debug(f"New DB connection for thread {threading.get_ident()}")
    return _thread_local.connection


def close_connection() -> None:
    if hasattr(_thread_local, "connection") and _thread_local.connection is not None:
        _thread_local.connection.close()
        _thread_local.connection = None


@contextmanager
def get_db_cursor():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def init_database() -> None:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id      TEXT PRIMARY KEY,
                    root_path    TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    total_files  INTEGER DEFAULT 0,
                    total_size   INTEGER DEFAULT 0,
                    scanned_at   TIMESTAMP,
                    duration_sec REAL DEFAULT 0.0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_files (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id    TEXT NOT NULL,
                    path       TEXT NOT NULL,
                    name       TEXT NOT NULL,
                    size       INTEGER NOT NULL,
                    extension  TEXT,
                    category   TEXT,
                    modified   TIMESTAMP,
                    created    TIMESTAMP,
                    hash       TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scans (scan_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_scan_id   ON scan_files(scan_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_category  ON scan_files(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_extension ON scan_files(extension)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_size      ON scan_files(size)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_path      ON scan_files(path)")
        logger.info(f"Database initialized at {DB_PATH} (WAL mode)")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def save_scan_metadata(
    scan_id: str, root_path: str, status: str,
    total_files: int = 0, total_size: int = 0,
    scanned_at: Optional[datetime] = None,
    duration_sec: float = 0.0,
) -> None:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO scans
                (scan_id, root_path, status, total_files, total_size, scanned_at, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (scan_id, root_path, status, total_files, total_size,
                  scanned_at or datetime.now(), duration_sec))
    except Exception as e:
        logger.error(f"Failed to save scan metadata: {e}")
        raise


def save_file_batch(scan_id: str, files: List[FileInfo]) -> None:
    if not files:
        return
    try:
        with get_db_cursor() as cursor:
            batch = [
                (
                    scan_id, f.path, f.name, f.size, f.extension,
                    f.category.value if hasattr(f.category, "value") else str(f.category),
                    f.modified, f.created, getattr(f, "hash", None),
                )
                for f in files
            ]
            cursor.executemany("""
                INSERT INTO scan_files
                (scan_id, path, name, size, extension, category, modified, created, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
    except Exception as e:
        logger.error(f"Failed to save file batch: {e}")
        raise


def get_scan(scan_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size,
                       scanned_at, duration_sec
                FROM scans WHERE scan_id = ?
            """, (scan_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get scan {scan_id}: {e}")
        return None


def get_files_paginated(
    scan_id: str, page: int = 1, page_size: int = 100,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        with get_db_cursor() as cursor:
            base_query  = "SELECT * FROM scan_files WHERE scan_id = ?"
            count_query = "SELECT COUNT(*) FROM scan_files WHERE scan_id = ?"
            params: list = [scan_id]

            if filters:
                for key, col in (("category", "category"), ("extension", "extension")):
                    if key in filters:
                        base_query  += f" AND {col} = ?"
                        count_query += f" AND {col} = ?"
                        params.append(filters[key])
                if "min_size" in filters:
                    base_query  += " AND size >= ?"
                    count_query += " AND size >= ?"
                    params.append(filters["min_size"])
                if "max_size" in filters:
                    base_query  += " AND size <= ?"
                    count_query += " AND size <= ?"
                    params.append(filters["max_size"])

            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            cursor.execute(
                base_query + " ORDER BY created DESC LIMIT ? OFFSET ?",
                params + [page_size, offset],
            )
            rows = cursor.fetchall()

            files = []
            for row in rows:
                fi = FileInfo(
                    path=row["path"], name=row["name"], size=row["size"],
                    extension=row["extension"] or "",
                    category=FileCategory(row["category"]) if row["category"] else FileCategory.OTHER,
                    modified=datetime.fromisoformat(row["modified"]) if row["modified"] else datetime.now(),
                    created=datetime.fromisoformat(row["created"])  if row["created"]  else datetime.now(),
                )
                if row["hash"]:
                    fi.hash = row["hash"]
                files.append(fi)

            return {
                "files": files,
                "total_files": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": max(1, (total_count + page_size - 1) // page_size),
            }
    except Exception as e:
        logger.error(f"Failed to get paginated files for {scan_id}: {e}")
        return {"files": [], "total_files": 0, "page": page,
                "page_size": page_size, "total_pages": 0}


def delete_scan_data(scan_id: str) -> None:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM scan_files WHERE scan_id = ?", (scan_id,))
            cursor.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
        logger.info(f"Deleted scan data for {scan_id}")
    except Exception as e:
        logger.error(f"Failed to delete scan data: {e}")
        raise


def get_scans() -> List[Dict[str, Any]]:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size,
                       scanned_at, duration_sec
                FROM scans ORDER BY scanned_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get scans: {e}")
        return []


def get_scan_statistics(scan_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size,
                       scanned_at, duration_sec
                FROM scans WHERE scan_id = ?
            """, (scan_id,))
            scan_row = cursor.fetchone()
            if not scan_row:
                return None
            cursor.execute("""
                SELECT category, COUNT(*) AS file_count, SUM(size) AS total_size
                FROM scan_files WHERE scan_id = ? AND category IS NOT NULL
                GROUP BY category ORDER BY total_size DESC
            """, (scan_id,))
            return {
                "scan_info": dict(scan_row),
                "category_stats": [dict(r) for r in cursor.fetchall()],
            }
    except Exception as e:
        logger.error(f"Failed to get statistics for {scan_id}: {e}")
        return None


# Inicializar al importar
try:
    init_database()
except Exception as e:
    logger.error(f"Failed to initialize database module: {e}")