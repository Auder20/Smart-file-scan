"""
Migration manager for SQLite database schema updates.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from .version import __version__

logger = logging.getLogger(__name__)


class Migration:
    """Base class for database migrations."""
    
    def __init__(self, version: str, description: str):
        self.version = version
        self.description = description
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply the migration (upgrade)."""
        raise NotImplementedError("Subclasses must implement up() method")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Reverse the migration (downgrade)."""
        raise NotImplementedError("Subclasses must implement down() method")


class MigrationManager:
    """Manages database migrations for SQLite."""
    
    def __init__(self, db_path: str, migrations_dir: Optional[str] = None):
        self.db_path = db_path
        self.migrations_dir = migrations_dir or os.path.dirname(__file__)
        self._ensure_migrations_table()
    
    def _ensure_migrations_table(self) -> None:
        """Ensure the migrations tracking table exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)
            conn.commit()
    
    def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            return [row[0] for row in cursor.fetchall()]
    
    def get_pending_migrations(self) -> List[Migration]:
        """Get list of pending migrations."""
        applied = set(self.get_applied_migrations())
        all_migrations = self._load_all_migrations()
        return [m for m in all_migrations if m.version not in applied]
    
    def _load_all_migrations(self) -> List[Migration]:
        """Load all migration classes from the migrations directory."""
        migrations = []
        
        # Import built-in migrations
        from . import builtin_migrations
        migrations.extend(builtin_migrations.ALL_MIGRATIONS)
        
        # Sort by version
        migrations.sort(key=lambda m: m.version)
        return migrations
    
    def migrate(self, target_version: Optional[str] = None) -> None:
        """
        Apply pending migrations up to target_version.
        
        Args:
            target_version: Target version to migrate to. If None, migrates to latest.
        """
        pending = self.get_pending_migrations()
        
        if target_version:
            pending = [m for m in pending if m.version <= target_version]
        
        if not pending:
            logger.info("No pending migrations to apply")
            return
        
        logger.info(f"Applying {len(pending)} migrations...")
        
        with sqlite3.connect(self.db_path) as conn:
            for migration in pending:
                logger.info(f"Applying migration {migration.version}: {migration.description}")
                
                try:
                    # Apply migration
                    migration.up(conn)
                    
                    # Record migration
                    conn.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                        (migration.version, migration.description)
                    )
                    conn.commit()
                    
                    logger.info(f"Successfully applied migration {migration.version}")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to apply migration {migration.version}: {e}")
                    raise RuntimeError(f"Migration {migration.version} failed: {e}")
    
    def rollback(self, target_version: str) -> None:
        """
        Rollback migrations to target_version.
        
        Args:
            target_version: Target version to rollback to
        """
        applied = self.get_applied_migrations()
        to_rollback = [v for v in applied if v > target_version]
        
        if not to_rollback:
            logger.info("No migrations to rollback")
            return
        
        logger.info(f"Rolling back {len(to_rollback)} migrations...")
        
        with sqlite3.connect(self.db_path) as conn:
            for version in reversed(to_rollback):
                migration = self._get_migration(version)
                if not migration:
                    logger.warning(f"Migration {version} not found, skipping")
                    continue
                
                logger.info(f"Rolling back migration {version}: {migration.description}")
                
                try:
                    # Rollback migration
                    migration.down(conn)
                    
                    # Remove migration record
                    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
                    conn.commit()
                    
                    logger.info(f"Successfully rolled back migration {version}")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to rollback migration {version}: {e}")
                    raise RuntimeError(f"Rollback {version} failed: {e}")
    
    def _get_migration(self, version: str) -> Optional[Migration]:
        """Get a specific migration by version."""
        all_migrations = self._load_all_migrations()
        for migration in all_migrations:
            if migration.version == version:
                return migration
        return None
    
    def get_current_version(self) -> str:
        """Get the current database version."""
        applied = self.get_applied_migrations()
        return max(applied) if applied else "0.0.0"
    
    def get_status(self) -> Dict[str, Any]:
        """Get migration status information."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()
        
        return {
            "current_version": self.get_current_version(),
            "latest_version": __version__,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied_migrations": applied,
            "pending_migrations": [m.version for m in pending]
        }
