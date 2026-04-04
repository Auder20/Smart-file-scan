"""
Migration runner for database initialization and updates.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .migrations.migration_manager import MigrationManager

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Handles database migration execution."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migration_manager = MigrationManager(db_path)
    
    def initialize_database(self) -> None:
        """
        Initialize database with all migrations.
        
        This should be called when setting up a new database
        or when the application starts.
        """
        logger.info(f"Initializing database at {self.db_path}")
        
        # Ensure database directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Run all pending migrations
        try:
            self.migration_manager.migrate()
            logger.info("Database initialization completed successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def check_migrations(self) -> dict:
        """
        Check migration status without applying them.
        
        Returns:
            Migration status information
        """
        return self.migration_manager.get_status()
    
    def migrate_to_latest(self) -> None:
        """Apply all pending migrations."""
        logger.info("Migrating database to latest version")
        
        status = self.check_migrations()
        if status["pending_count"] > 0:
            logger.info(f"Found {status['pending_count']} pending migrations")
            self.migration_manager.migrate()
            logger.info("Migration to latest completed")
        else:
            logger.info("Database is already at latest version")
    
    def rollback_to_version(self, target_version: str) -> None:
        """
        Rollback database to specific version.
        
        Args:
            target_version: Target version to rollback to
        """
        logger.info(f"Rolling back database to version {target_version}")
        self.migration_manager.rollback(target_version)
        logger.info(f"Rollback to {target_version} completed")
    
    def get_current_version(self) -> str:
        """Get current database version."""
        return self.migration_manager.get_current_version()


# Global migration runner instance
_migration_runner: MigrationRunner | None = None


def get_migration_runner(db_path: str) -> MigrationRunner:
    """
    Get or create migration runner instance.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        MigrationRunner instance
    """
    global _migration_runner
    
    if _migration_runner is None or _migration_runner.db_path != db_path:
        _migration_runner = MigrationRunner(db_path)
    
    return _migration_runner
