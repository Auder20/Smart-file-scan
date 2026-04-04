"""
Database migrations for Smart File Organizer.

This module provides version-controlled schema migrations for the SQLite database.
"""

from .migration_manager import MigrationManager
from .version import __version__

__all__ = ['MigrationManager', '__version__']
