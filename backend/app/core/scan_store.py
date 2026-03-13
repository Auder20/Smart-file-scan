"""
ARCH 2: Centralized scan state management singleton

This module provides a centralized way to access and manage scan state,
eliminating direct coupling between routers through global variables.
"""

import logging
from typing import Dict, Optional
from threading import Lock
from datetime import datetime

from app.models.file_info import ScanResult, ScanProgress, ScanStatus

logger = logging.getLogger(__name__)


class ScanStore:
    """Singleton for managing scan state across the application"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        
        self._scan_results: Dict[str, ScanResult] = {}
        self._scan_progress: Dict[str, ScanProgress] = {}
        self._initialized = True
        logger.debug("ScanStore singleton initialized")
    
    # Scan Results Management
    def get_scan_result(self, scan_id: str) -> Optional[ScanResult]:
        """Get scan result by ID"""
        return self._scan_results.get(scan_id)
    
    def set_scan_result(self, scan_id: str, result: ScanResult) -> None:
        """Set scan result"""
        self._scan_results[scan_id] = result
        logger.debug(f"Stored scan result for {scan_id}")
    
    def remove_scan_result(self, scan_id: str) -> Optional[ScanResult]:
        """Remove and return scan result"""
        return self._scan_results.pop(scan_id, None)
    
    def has_scan_result(self, scan_id: str) -> bool:
        """Check if scan result exists"""
        return scan_id in self._scan_results
    
    def get_all_scan_results(self) -> Dict[str, ScanResult]:
        """Get all scan results"""
        return self._scan_results.copy()
    
    # Scan Progress Management
    def get_scan_progress(self, scan_id: str) -> Optional[ScanProgress]:
        """Get scan progress by ID"""
        return self._scan_progress.get(scan_id)
    
    def set_scan_progress(self, scan_id: str, progress: ScanProgress) -> None:
        """Set scan progress"""
        self._scan_progress[scan_id] = progress
        logger.debug(f"Stored scan progress for {scan_id}")
    
    def remove_scan_progress(self, scan_id: str) -> Optional[ScanProgress]:
        """Remove and return scan progress"""
        return self._scan_progress.pop(scan_id, None)
    
    def has_scan_progress(self, scan_id: str) -> bool:
        """Check if scan progress exists"""
        return scan_id in self._scan_progress
    
    def get_all_scan_progress(self) -> Dict[str, ScanProgress]:
        """Get all scan progress"""
        return self._scan_progress.copy()
    
    # Combined Operations
    def remove_scan(self, scan_id: str) -> tuple[Optional[ScanResult], Optional[ScanProgress]]:
        """Remove both scan result and progress"""
        result = self.remove_scan_result(scan_id)
        progress = self.remove_scan_progress(scan_id)
        return result, progress
    
    def get_scan_info(self, scan_id: str) -> Optional[Dict]:
        """Get combined scan information"""
        progress = self.get_scan_progress(scan_id)
        result = self.get_scan_result(scan_id)
        
        if not progress and not result:
            return None
        
        info = {
            "scan_id": scan_id,
            "status": progress.status if progress else "unknown",
            "files_found": progress.files_found if progress else 0,
            "progress": progress.progress if progress else 0,
            "message": progress.message if progress else "",
        }
        
        if result:
            info.update({
                "root_path": result.root_path,
                "total_files": result.total_files,
                "total_size": result.total_size,
                "scanned_at": result.scanned_at.isoformat(),
                "duration_sec": result.duration_sec,
                "files_truncated": result.files_truncated,
            })
        
        return info
    
    def get_all_scans_info(self) -> list[Dict]:
        """Get information for all scans"""
        all_scan_ids = set(self._scan_progress.keys()) | set(self._scan_results.keys())
        scans_info = []
        
        for scan_id in all_scan_ids:
            info = self.get_scan_info(scan_id)
            if info:
                scans_info.append(info)
        
        # Sort by scanned_at (most recent first)
        scans_info.sort(key=lambda x: x.get("scanned_at") or "", reverse=True)
        return scans_info
    
    # Batch Operations
    def clear_all(self) -> None:
        """Clear all scan data"""
        self._scan_results.clear()
        self._scan_progress.clear()
        logger.info("Cleared all scan data from store")
    
    def get_completed_scans_count(self) -> int:
        """Get count of completed scans"""
        return sum(1 for p in self._scan_progress.values() 
                  if p.status == ScanStatus.COMPLETED)
    
    def get_running_scans_count(self) -> int:
        """Get count of running scans"""
        return sum(1 for p in self._scan_progress.values() 
                  if p.status == ScanStatus.RUNNING)


# Global singleton instance
scan_store = ScanStore()
