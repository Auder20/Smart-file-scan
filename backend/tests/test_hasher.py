"""
Unit tests for hasher duplicate detection functionality.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.core.hasher import find_duplicates_from_sqlite, _CHUNK_SIZE, _PARTIAL_SIZE


class TestHasher:
    """Test hasher duplicate detection functionality."""
    
    def test_constants(self):
        """Test hasher constants are properly set."""
        assert _CHUNK_SIZE == 8 * 1024  # 8KB
        assert _PARTIAL_SIZE == 4 * 1024  # 4KB
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_empty_scan(self, mock_get_files):
        """Test duplicate detection with empty scan."""
        mock_get_files.return_value = {
            "files": [],
            "total_files": 0,
            "total_pages": 0
        }
        
        duplicates = find_duplicates_from_sqlite("empty_scan")
        assert duplicates == []
        mock_get_files.assert_called_once_with("empty_scan", 1, 5000)
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_no_duplicates(self, mock_get_files):
        """Test duplicate detection with no duplicate files."""
        files = [
            Mock(id=1, path="/file1.txt", size=1000, file_hash="hash1"),
            Mock(id=2, path="/file2.txt", size=2000, file_hash="hash2"),
            Mock(id=3, path="/file3.txt", size=3000, file_hash="hash3"),
        ]
        mock_get_files.return_value = {
            "files": files,
            "total_files": 3,
            "total_pages": 1
        }
        
        duplicates = find_duplicates_from_sqlite("scan_no_dups")
        assert duplicates == []
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_simple_case(self, mock_get_files):
        """Test duplicate detection with simple duplicate case."""
        files = [
            Mock(id=1, path="/file1.txt", size=1000, file_hash="hash1"),
            Mock(id=2, path="/file2.txt", size=1000, file_hash="hash1"),  # Duplicate
            Mock(id=3, path="/file3.txt", size=2000, file_hash="hash2"),
        ]
        mock_get_files.return_value = {
            "files": files,
            "total_files": 3,
            "total_pages": 1
        }
        
        duplicates = find_duplicates_from_sqlite("scan_with_dups")
        
        assert len(duplicates) == 1
        assert duplicates[0].file_hash == "hash1"
        assert duplicates[0].total_files == 2
        assert duplicates[0].total_size == 2000
        assert len(duplicates[0].files) == 2
        assert duplicates[0].files[0].path == "/file1.txt"
        assert duplicates[0].files[1].path == "/file2.txt"
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_multiple_groups(self, mock_get_files):
        """Test duplicate detection with multiple duplicate groups."""
        files = [
            Mock(id=1, path="/file1.txt", size=1000, file_hash="hash1"),
            Mock(id=2, path="/file2.txt", size=1000, file_hash="hash1"),  # Duplicate 1
            Mock(id=3, path="/file3.txt", size=2000, file_hash="hash2"),
            Mock(id=4, path="/file4.txt", size=2000, file_hash="hash2"),  # Duplicate 2
            Mock(id=5, path="/file5.txt", size=2000, file_hash="hash2"),  # Duplicate 2
            Mock(id=6, path="/file6.txt", size=3000, file_hash="hash3"),
        ]
        mock_get_files.return_value = {
            "files": files,
            "total_files": 6,
            "total_pages": 1
        }
        
        duplicates = find_duplicates_from_sqlite("scan_multi_dups")
        
        assert len(duplicates) == 2
        
        # First duplicate group
        dup1 = next(d for d in duplicates if d.file_hash == "hash1")
        assert dup1.total_files == 2
        assert dup1.total_size == 2000
        assert len(dup1.files) == 2
        
        # Second duplicate group
        dup2 = next(d for d in duplicates if d.file_hash == "hash2")
        assert dup2.total_files == 3
        assert dup2.total_size == 6000
        assert len(dup2.files) == 3
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_with_progress_callback(self, mock_get_files):
        """Test duplicate detection with progress callback."""
        files = [
            Mock(id=1, path="/file1.txt", size=1000, file_hash="hash1"),
            Mock(id=2, path="/file2.txt", size=1000, file_hash="hash1"),
        ]
        mock_get_files.return_value = {
            "files": files,
            "total_files": 2,
            "total_pages": 1
        }
        
        progress_calls = []
        def progress_callback(current, total):
            progress_calls.append((current, total))
        
        duplicates = find_duplicates_from_sqlite("scan", progress_callback)
        
        # Should have at least one progress call
        assert len(progress_calls) > 0
        assert all(0 <= current <= total for current, total in progress_calls)
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_max_files_limit(self, mock_get_files):
        """Test duplicate detection with max_files limit."""
        # Create many files
        files = [Mock(id=i, path=f"/file{i}.txt", size=1000, file_hash=f"hash{i%5}") 
                 for i in range(100)]
        
        mock_get_files.return_value = {
            "files": files,
            "total_files": 100,
            "total_pages": 1
        }
        
        # Test with max_files=30
        duplicates = find_duplicates_from_sqlite("scan", max_files=30)
        
        # Should process only first 30 files
        mock_get_files.assert_called_with("scan", 1, 5000)
        # Verify that only first 30 files were considered
        processed_files = mock_get_files.return_value["files"]
        assert len(processed_files) == 30
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_chunked_processing(self, mock_get_files):
        """Test duplicate detection with chunked processing."""
        # First page
        files_page1 = [
            Mock(id=1, path="/file1.txt", size=1000, file_hash="hash1"),
            Mock(id=2, path="/file2.txt", size=1000, file_hash="hash1"),
        ]
        # Second page
        files_page2 = [
            Mock(id=3, path="/file3.txt", size=2000, file_hash="hash2"),
            Mock(id=4, path="/file4.txt", size=2000, file_hash="hash2"),
        ]
        
        mock_get_files.side_effect = [
            {"files": files_page1, "total_files": 4, "total_pages": 2},
            {"files": files_page2, "total_files": 4, "total_pages": 2},
        ]
        
        duplicates = find_duplicates_from_sqlite("scan", chunk_size=2)
        
        # Should find both duplicate groups
        assert len(duplicates) == 2
        
        # Verify pagination calls
        assert mock_get_files.call_count == 2
        mock_get_files.assert_any_call("scan", 1, 2)
        mock_get_files.assert_any_call("scan", 2, 2)
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_error_handling(self, mock_get_files):
        """Test error handling in duplicate detection."""
        mock_get_files.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            find_duplicates_from_sqlite("scan")
    
    @patch('app.core.hasher.get_files_paginated')
    def test_find_duplicates_sorting(self, mock_get_files):
        """Test that duplicate groups are sorted by total_size descending."""
        files = [
            Mock(id=1, path="/small1.txt", size=100, file_hash="hash_small"),
            Mock(id=2, path="/small2.txt", size=100, file_hash="hash_small"),
            Mock(id=3, path="/large1.txt", size=1000, file_hash="hash_large"),
            Mock(id=4, path="/large2.txt", size=1000, file_hash="hash_large"),
            Mock(id=5, path="/large3.txt", size=1000, file_hash="hash_large"),
        ]
        mock_get_files.return_value = {
            "files": files,
            "total_files": 5,
            "total_pages": 1
        }
        
        duplicates = find_duplicates_from_sqlite("scan")
        
        # Should be sorted by total_size descending
        assert len(duplicates) == 2
        assert duplicates[0].total_size == 3000  # Large duplicates
        assert duplicates[1].total_size == 200   # Small duplicates
        
        assert duplicates[0].file_hash == "hash_large"
        assert duplicates[1].file_hash == "hash_small"


class TestFileHashing:
    """Test file hashing functionality."""
    
    def test_file_hashing_integration(self):
        """Test actual file hashing with temporary files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files with identical content
            file1_path = Path(temp_dir) / "file1.txt"
            file2_path = Path(temp_dir) / "file2.txt"
            file3_path = Path(temp_dir) / "file3.txt"
            
            content = b"Test content for hashing"
            file1_path.write_bytes(content)
            file2_path.write_bytes(content)  # Same content
            file3_path.write_bytes(b"Different content")  # Different content
            
            # Mock the database functions to use our test files
            with patch('app.core.hasher.get_files_paginated') as mock_get_files:
                files = [
                    Mock(id=1, path=str(file1_path), size=len(content), file_hash=None),
                    Mock(id=2, path=str(file2_path), size=len(content), file_hash=None),
                    Mock(id=3, path=str(file3_path), size=len(b"Different content"), file_hash=None),
                ]
                mock_get_files.return_value = {
                    "files": files,
                    "total_files": 3,
                    "total_pages": 1
                }
                
                # Mock the hash calculation to use actual file hashing
                def mock_calculate_hash(file_path, chunk_size=_CHUNK_SIZE):
                    import hashlib
                    hasher = hashlib.md5()
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(chunk_size):
                            hasher.update(chunk)
                    return hasher.hexdigest()
                
                with patch('app.core.hasher._calculate_file_hash', side_effect=mock_calculate_hash):
                    duplicates = find_duplicates_from_sqlite("test_scan")
                
                # Should find one duplicate group (file1 and file2)
                assert len(duplicates) == 1
                assert duplicates[0].total_files == 2
                assert duplicates[0].total_size == len(content) * 2


if __name__ == "__main__":
    pytest.main([__file__])
