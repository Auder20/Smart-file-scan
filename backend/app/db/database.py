from __future__ import annotations

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import threading

from app.models.file_info import FileInfo, FileCategory

logger = logging.getLogger(__name__)

# Database configuration
DB_PATH = "smart_file_organizer.db"

# ARCH 3: Thread-local connection pool
_thread_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """Get database connection from thread-local pool"""
    # Check if connection already exists for this thread
    if not hasattr(_thread_local, 'connection') or _thread_local.connection is None:
        _thread_local.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _thread_local.connection.row_factory = sqlite3.Row  # Enable dict-like row access
        logger.debug(f"Created new database connection for thread {threading.get_ident()}")
    
    return _thread_local.connection

def close_connection() -> None:
    """Close the connection for current thread"""
    if hasattr(_thread_local, 'connection') and _thread_local.connection is not None:
        _thread_local.connection.close()
        _thread_local.connection = None
        logger.debug(f"Closed database connection for thread {threading.get_ident()}")

@contextmanager
def get_db_cursor():
    """Context manager for database cursor using thread-local connection"""
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
    """Initialize database tables"""
    try:
        with get_db_cursor() as cursor:
            # Create scans table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_files INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    scanned_at TIMESTAMP,
                    duration_sec REAL DEFAULT 0.0
                )
            """)
            
            # Create scan_files table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    extension TEXT,
                    category TEXT,
                    modified TIMESTAMP,
                    created TIMESTAMP,
                    hash TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scans (scan_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_scan_id ON scan_files(scan_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_category ON scan_files(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_extension ON scan_files(extension)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_size ON scan_files(size)")
            
            logger.info("Database initialized successfully")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def save_scan_metadata(scan_id: str, root_path: str, status: str, 
                    total_files: int = 0, total_size: int = 0, 
                    scanned_at: Optional[datetime] = None, 
                    duration_sec: float = 0.0) -> None:
    """Save scan metadata to database"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO scans 
                (scan_id, root_path, status, total_files, total_size, scanned_at, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id, root_path, status, total_files, total_size,
                scanned_at or datetime.now(), duration_sec
            ))
        logger.debug(f"Saved scan metadata for {scan_id}")
    except Exception as e:
        logger.error(f"Failed to save scan metadata: {e}")
        raise

def save_file_batch(scan_id: str, files: List[FileInfo]) -> None:
    """Save a batch of files to database efficiently"""
    if not files:
        return
        
    try:
        with get_db_cursor() as cursor:
            # Prepare batch data
            batch_data = []
            for file_info in files:
                batch_data.append((
                    scan_id,
                    file_info.path,
                    file_info.name,
                    file_info.size,
                    file_info.extension,
                    file_info.category.value if hasattr(file_info.category, 'value') else str(file_info.category),
                    file_info.modified,
                    file_info.created,
                    getattr(file_info, 'hash', None)
                ))
            
            # Execute batch insert
            cursor.executemany("""
                INSERT INTO scan_files 
                (scan_id, path, name, size, extension, category, modified, created, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch_data)
            
        logger.debug(f"Saved batch of {len(files)} files for scan {scan_id}")
    except Exception as e:
        logger.error(f"Failed to save file batch: {e}")
        raise

def get_scan(scan_id: str) -> Optional[Dict[str, Any]]:
    """Get scan metadata by ID"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size, 
                       scanned_at, duration_sec
                FROM scans WHERE scan_id = ?
            """, (scan_id,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Failed to get scan {scan_id}: {e}")
        return None

def get_files_paginated(scan_id: str, page: int = 1, page_size: int = 100, 
                      filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get paginated files for a scan with optional filters"""
    try:
        with get_db_cursor() as cursor:
            # Build base query
            base_query = "SELECT * FROM scan_files WHERE scan_id = ?"
            count_query = "SELECT COUNT(*) FROM scan_files WHERE scan_id = ?"
            params = [scan_id]
            
            # Add filters
            if filters:
                if 'category' in filters:
                    base_query += " AND category = ?"
                    count_query += " AND category = ?"
                    params.append(filters['category'])
                
                if 'extension' in filters:
                    base_query += " AND extension = ?"
                    count_query += " AND extension = ?"
                    params.append(filters['extension'])
                
                if 'min_size' in filters:
                    base_query += " AND size >= ?"
                    count_query += " AND size >= ?"
                    params.append(filters['min_size'])
                
                if 'max_size' in filters:
                    base_query += " AND size <= ?"
                    count_query += " AND size <= ?"
                    params.append(filters['max_size'])
            
            # Get total count
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Add pagination
            offset = (page - 1) * page_size
            base_query += " ORDER BY created DESC LIMIT ? OFFSET ?"
            params.extend([page_size, offset])
            
            # Get files
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            
            # Convert to FileInfo objects
            files = []
            for row in rows:
                file_info = FileInfo(
                    path=row['path'],
                    name=row['name'],
                    size=row['size'],
                    extension=row['extension'] or '',
                    category=FileCategory(row['category']) if row['category'] else FileCategory.OTHER,
                    modified=datetime.fromisoformat(row['modified']) if row['modified'] else datetime.now(),
                    created=datetime.fromisoformat(row['created']) if row['created'] else datetime.now(),
                )
                if row['hash']:
                    file_info.hash = row['hash']
                files.append(file_info)
            
            return {
                'files': files,
                'total_files': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            }
            
    except Exception as e:
        logger.error(f"Failed to get paginated files for scan {scan_id}: {e}")
        return {
            'files': [],
            'total_files': 0,
            'page': page,
            'page_size': page_size,
            'total_pages': 0
        }

def delete_scan_data(scan_id: str) -> None:
    """Delete scan and all associated files"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM scan_files WHERE scan_id = ?", (scan_id,))
            cursor.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
        logger.info(f"Deleted scan data for {scan_id}")
    except Exception as e:
        logger.error(f"Failed to delete scan data for {scan_id}: {e}")
        raise

def get_scans() -> List[Dict[str, Any]]:
    """Get all scans"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size, 
                       scanned_at, duration_sec
                FROM scans 
                ORDER BY scanned_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get scans: {e}")
        return []

def get_scan_statistics(scan_id: str) -> Optional[Dict[str, Any]]:
    """Get statistics for a scan"""
    try:
        with get_db_cursor() as cursor:
            # Get basic scan info
            cursor.execute("""
                SELECT scan_id, root_path, status, total_files, total_size, 
                       scanned_at, duration_sec
                FROM scans WHERE scan_id = ?
            """, (scan_id,))
            
            scan_row = cursor.fetchone()
            if not scan_row:
                return None
            
            # Get category breakdown
            cursor.execute("""
                SELECT category, COUNT(*) as file_count, SUM(size) as total_size
                FROM scan_files 
                WHERE scan_id = ? AND category IS NOT NULL
                GROUP BY category
                ORDER BY total_size DESC
            """, (scan_id,))
            
            category_stats = []
            for row in cursor.fetchall():
                category_stats.append({
                    'category': row['category'],
                    'file_count': row['file_count'],
                    'total_size': row['total_size']
                })
            
            return {
                'scan_info': dict(scan_row),
                'category_stats': category_stats
            }
            
    except Exception as e:
        logger.error(f"Failed to get statistics for scan {scan_id}: {e}")
        return None

# Initialize database on module import
try:
    init_database()
except Exception as e:
    logger.error(f"Failed to initialize database module: {e}")
