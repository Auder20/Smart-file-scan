"""
Built-in database migrations for Smart File Organizer.
"""

import sqlite3
from .migration_manager import Migration


# Migration 001: Initial database schema
class Migration_001_InitialSchema(Migration):
    """Create initial database schema for scans and files."""
    
    def __init__(self):
        super().__init__("1.0.0", "Initial database schema with scans and files tables")
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Create initial schema."""
        # Create scans table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                root_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                total_files INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                scanned_at TIMESTAMP,
                duration_sec REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create scan_files table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                extension TEXT,
                category TEXT DEFAULT 'other',
                modified TIMESTAMP,
                file_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for better performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_scan_id ON scan_files(scan_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_path ON scan_files(path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_extension ON scan_files(extension)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_category ON scan_files(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_file_hash ON scan_files(file_hash)")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove initial schema."""
        conn.execute("DROP TABLE IF EXISTS scan_files")
        conn.execute("DROP TABLE IF EXISTS scans")


# Migration 002: Add duplicate tracking
class Migration_002_DuplicateTracking(Migration):
    """Add duplicate file tracking functionality."""
    
    def __init__(self):
        super().__init__("1.1.0", "Add duplicate file tracking with groups")
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Add duplicate tracking tables."""
        # Create duplicate_groups table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)
        
        # Create duplicate_files table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES duplicate_groups (id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES scan_files (id) ON DELETE CASCADE
            )
        """)
        
        # Add indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_groups_scan_id ON duplicate_groups(scan_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_groups_file_hash ON duplicate_groups(file_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_files_group_id ON duplicate_files(group_id)")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove duplicate tracking tables."""
        conn.execute("DROP TABLE IF EXISTS duplicate_files")
        conn.execute("DROP TABLE IF EXISTS duplicate_groups")


# Migration 003: Add scan statistics
class Migration_003_ScanStatistics(Migration):
    """Add scan statistics and performance tracking."""
    
    def __init__(self):
        super().__init__("1.2.0", "Add scan statistics and performance tracking")
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Add statistics tracking."""
        # Add performance columns to scans table
        conn.execute("ALTER TABLE scans ADD COLUMN files_per_second REAL DEFAULT 0")
        conn.execute("ALTER TABLE scans ADD COLUMN avg_file_size REAL DEFAULT 0")
        conn.execute("ALTER TABLE scans ADD COLUMN largest_file_size INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE scans ADD COLUMN smallest_file_size INTEGER DEFAULT 0")
        
        # Create scan_statistics table for detailed metrics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                category TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                avg_size REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)
        
        # Add indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_statistics_scan_id ON scan_statistics(scan_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_statistics_category ON scan_statistics(category)")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove statistics tracking."""
        conn.execute("DROP TABLE IF EXISTS scan_statistics")
        # Note: SQLite doesn't support DROP COLUMN, so we keep the added columns


# List all built-in migrations
ALL_MIGRATIONS = [
    Migration_001_InitialSchema(),
    Migration_002_DuplicateTracking(),
    Migration_003_ScanStatistics(),
]
