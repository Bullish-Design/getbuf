"""Test filesystem utilities for GetBuf."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from getbuf.fs import (
    IGNORE_EXTENSIONS,
    IGNORE_PATTERNS,
    clean_directory_contents,
    compute_written_files,
    ensure_directory_exists,
    snapshot_directory,
)
from getbuf.models import CleanError, CleanOperation, FileSnapshot


class TestCleanDirectoryContents:
    """Test directory cleaning operations."""

    def test_clean_existing_directory_with_files(self):
        """Test cleaning directory that contains files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create files and subdirectory
            (target / "file1.txt").write_text("content1")
            (target / "file2.py").write_text("content2")
            subdir = target / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("nested")

            # Clean the directory
            result = clean_directory_contents(target)

            assert isinstance(result, CleanOperation)
            assert result.target_dir == target.resolve()
            assert result.cleaned is True
            assert len(result.files_removed) == 3
            assert "file1.txt" in result.files_removed
            assert "file2.py" in result.files_removed
            assert "subdir/" in result.files_removed

            # Directory should still exist but be empty
            assert target.exists()
            assert target.is_dir()
            assert list(target.iterdir()) == []

    def test_clean_empty_directory(self):
        """Test cleaning an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "empty"
            target.mkdir()

            result = clean_directory_contents(target)

            assert result.cleaned is True
            assert result.files_removed == []
            assert target.exists()
            assert target.is_dir()

    def test_clean_nonexistent_directory(self):
        """Test cleaning directory that doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nonexistent"

            result = clean_directory_contents(target)

            assert result.cleaned is False
            assert result.files_removed == []
            assert result.target_dir == target.resolve()

    def test_clean_file_instead_of_directory(self):
        """Test error when target is a file instead of directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "file.txt"
            target.write_text("content")

            with pytest.raises(CleanError, match="must be a directory"):
                clean_directory_contents(target)

    def test_clean_permission_error(self):
        """Test handling of permission errors during cleaning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "protected"
            target.mkdir()
            test_file = target / "file.txt"
            test_file.write_text("content")

            # Mock unlink to raise PermissionError
            with patch.object(Path, "unlink") as mock_unlink:
                mock_unlink.side_effect = PermissionError("Access denied")

                with pytest.raises(CleanError, match="Failed to remove"):
                    clean_directory_contents(target)

    def test_clean_nested_directories(self):
        """Test cleaning deeply nested directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create nested structure
            deep_dir = target / "a" / "b" / "c"
            deep_dir.mkdir(parents=True)
            (deep_dir / "deep.txt").write_text("deep content")
            (target / "root.txt").write_text("root content")

            result = clean_directory_contents(target)

            assert result.cleaned is True
            assert len(result.files_removed) == 2
            assert "root.txt" in result.files_removed
            assert "a/" in result.files_removed
            assert target.exists()
            assert list(target.iterdir()) == []


class TestSnapshotDirectory:
    """Test directory snapshot operations."""

    def test_snapshot_directory_with_files(self):
        """Test creating snapshot of directory with files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create files
            file1 = target / "file1.txt"
            file2 = target / "subdir" / "file2.py"
            file2.parent.mkdir()

            file1.write_text("content1")
            file2.write_text("content2")

            snapshot = snapshot_directory(target)

            assert isinstance(snapshot, FileSnapshot)
            assert len(snapshot.files) == 2
            assert "file1.txt" in snapshot.files
            assert "subdir/file2.py" in snapshot.files

            # Check that modification times are recorded
            assert snapshot.files["file1.txt"] > 0
            assert snapshot.files["subdir/file2.py"] > 0
            assert snapshot.timestamp is not None

    def test_snapshot_empty_directory(self):
        """Test snapshot of empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "empty"
            target.mkdir()

            snapshot = snapshot_directory(target)

            assert len(snapshot.files) == 0
            assert snapshot.timestamp is not None

    def test_snapshot_nonexistent_directory(self):
        """Test snapshot of directory that doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nonexistent"

            snapshot = snapshot_directory(target)

            assert len(snapshot.files) == 0
            assert snapshot.timestamp is not None

    def test_snapshot_file_instead_of_directory(self):
        """Test snapshot when target is a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "file.txt"
            target.write_text("content")

            snapshot = snapshot_directory(target)

            assert len(snapshot.files) == 0

    def test_snapshot_handles_permission_errors(self):
        """Test snapshot gracefully handles file permission errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create a file
            good_file = target / "good.txt"
            good_file.write_text("good content")

            # Mock stat to fail for one file
            original_stat = Path.stat

            def mock_stat(self):
                if self.name == "good.txt":
                    return original_stat(self)
                raise OSError("Permission denied")

            with patch.object(Path, "stat", mock_stat):
                snapshot = snapshot_directory(target)

            # Should still get the files that worked
            assert "good.txt" in snapshot.files

    def test_snapshot_path_normalization(self):
        """Test that snapshot uses forward slashes consistently."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create nested file
            nested_dir = target / "a" / "b"
            nested_dir.mkdir(parents=True)
            (nested_dir / "nested.txt").write_text("content")

            snapshot = snapshot_directory(target)

            # Should use forward slashes regardless of OS
            assert "a/b/nested.txt" in snapshot.files


class TestComputeWrittenFiles:
    """Test file difference computation."""

    def test_compute_new_files(self):
        """Test detecting new files between snapshots."""
        before = FileSnapshot(timestamp=None, files={"existing.txt": 1000.0})

        after = FileSnapshot(
            timestamp=None,
            files={
                "existing.txt": 1000.0,  # Unchanged
                "new.txt": 2000.0,  # New file
                "another.py": 3000.0,  # Another new file
            },
        )

        written = compute_written_files(before, after)

        assert len(written) == 2
        assert "new.txt" in written
        assert "another.py" in written
        assert "existing.txt" not in written

    def test_compute_modified_files(self):
        """Test detecting modified files."""
        before = FileSnapshot(
            timestamp=None, files={"file1.txt": 1000.0, "file2.py": 2000.0}
        )

        after = FileSnapshot(
            timestamp=None,
            files={
                "file1.txt": 1500.0,  # Modified
                "file2.py": 2000.0,  # Unchanged
            },
        )

        written = compute_written_files(before, after)

        assert written == ["file1.txt"]

    def test_compute_ignores_patterns(self):
        """Test that ignore patterns are applied correctly."""
        before = FileSnapshot(timestamp=None, files={})

        after = FileSnapshot(
            timestamp=None,
            files={
                "good.py": 1000.0,
                "__pycache__/module.pyc": 2000.0,
                "test.pyc": 3000.0,
                ".mypy_cache/cache.json": 4000.0,
                ".DS_Store": 5000.0,
                "subdir/__pycache__/cached.pyc": 6000.0,
            },
        )

        written = compute_written_files(before, after)

        # Only good.py should be included
        assert written == ["good.py"]

    def test_compute_empty_snapshots(self):
        """Test with empty snapshots."""
        before = FileSnapshot(timestamp=None, files={})
        after = FileSnapshot(timestamp=None, files={})

        written = compute_written_files(before, after)

        assert written == []

    def test_compute_deterministic_order(self):
        """Test that results are returned in deterministic order."""
        before = FileSnapshot(timestamp=None, files={})

        after = FileSnapshot(
            timestamp=None,
            files={"zebra.py": 1000.0, "alpha.py": 2000.0, "beta.py": 3000.0},
        )

        written = compute_written_files(before, after)

        # Should be sorted alphabetically
        assert written == ["alpha.py", "beta.py", "zebra.py"]


class TestEnsureDirectoryExists:
    """Test directory creation utility."""

    def test_create_nonexistent_directory(self):
        """Test creating directory that doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "new_dir"

            ensure_directory_exists(target)

            assert target.exists()
            assert target.is_dir()

    def test_create_nested_directories(self):
        """Test creating nested directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "a" / "b" / "c"

            ensure_directory_exists(target)

            assert target.exists()
            assert target.is_dir()
            assert target.parent.exists()
            assert target.parent.parent.exists()

    def test_existing_directory_no_op(self):
        """Test that existing directory is left alone."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "existing"
            target.mkdir()

            # Should not raise
            ensure_directory_exists(target)

            assert target.exists()
            assert target.is_dir()

    def test_path_is_file_error(self):
        """Test error when path exists but is a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "file.txt"
            target.write_text("content")

            with pytest.raises(CleanError, match="not a directory"):
                ensure_directory_exists(target)

    def test_permission_error(self):
        """Test handling of permission errors during creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "protected"

            # Mock mkdir to raise PermissionError
            with patch.object(Path, "mkdir") as mock_mkdir:
                mock_mkdir.side_effect = PermissionError("Access denied")

                with pytest.raises(CleanError, match="Failed to create"):
                    ensure_directory_exists(target)


class TestIgnorePatterns:
    """Test ignore pattern constants and behavior."""

    def test_ignore_patterns_defined(self):
        """Test that ignore patterns are properly defined."""
        assert "__pycache__" in IGNORE_PATTERNS
        assert ".mypy_cache" in IGNORE_PATTERNS
        assert ".pytest_cache" in IGNORE_PATTERNS
        assert ".DS_Store" in IGNORE_PATTERNS

    def test_ignore_extensions_defined(self):
        """Test that ignore extensions are properly defined."""
        assert ".pyc" in IGNORE_EXTENSIONS

    def test_ignore_functionality_with_real_files(self):
        """Integration test of ignore patterns with real file operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target"
            target.mkdir()

            # Create files that should be ignored
            pycache = target / "__pycache__"
            pycache.mkdir()
            (pycache / "module.cpython-39.pyc").write_text("bytecode")

            (target / "test.pyc").write_text("compiled")
            (target / ".DS_Store").write_text("system")

            # Create file that should NOT be ignored
            (target / "good.py").write_text("source")

            # Test snapshot and diff
            before = snapshot_directory(Path(temp_dir) / "empty")
            after = snapshot_directory(target)

            written = compute_written_files(before, after)

            # Only the good file should be detected
            assert "good.py" in written
            assert len([f for f in written if "pycache" in f]) == 0
            assert len([f for f in written if f.endswith(".pyc")]) == 0
            assert ".DS_Store" not in written
