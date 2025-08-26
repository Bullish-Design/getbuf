"""Filesystem utilities for GetBuf operations."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from getbuf.logging import logger
from getbuf.models import CleanError, CleanOperation, FileSnapshot

# File patterns to ignore when computing written files
IGNORE_PATTERNS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".DS_Store"}

# File extensions to ignore
IGNORE_EXTENSIONS = {".pyc"}


def clean_directory_contents(target_dir: Path) -> CleanOperation:
    """
    Remove contents of directory while preserving the directory itself.

    Args:
        target_dir: Directory whose contents should be cleaned

    Returns:
        CleanOperation: Result of the cleaning operation

    Raises:
        CleanError: If cleaning fails due to permissions or other issues
    """
    logger.debug("Starting directory clean", target_dir=str(target_dir))

    # Ensure target_dir is absolute
    target_dir = target_dir.resolve()

    # Handle case where directory doesn't exist
    if not target_dir.exists():
        logger.info(
            "Clean target directory does not exist, no-op", target_dir=str(target_dir)
        )
        return CleanOperation(target_dir=target_dir, cleaned=False, files_removed=[])

    if not target_dir.is_dir():
        raise CleanError(f"Clean target must be a directory: {target_dir}")

    files_removed = []

    try:
        # List all items in the directory
        for item in target_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    files_removed.append(str(item.relative_to(target_dir)))
                    logger.debug("Removed file", file=str(item))
                elif item.is_dir():
                    shutil.rmtree(item)
                    files_removed.append(str(item.relative_to(target_dir)) + "/")
                    logger.debug("Removed directory", directory=str(item))
            except (OSError, PermissionError) as e:
                logger.error(
                    "Failed to remove item during clean", item=str(item), error=str(e)
                )
                raise CleanError(f"Failed to remove {item}: {e}") from e

        logger.info(
            "Directory contents cleaned successfully",
            target_dir=str(target_dir),
            files_removed=len(files_removed),
        )

        return CleanOperation(
            target_dir=target_dir, cleaned=True, files_removed=files_removed
        )

    except Exception as e:
        if isinstance(e, CleanError):
            raise
        logger.error(
            "Unexpected error during directory clean",
            target_dir=str(target_dir),
            error=str(e),
        )
        raise CleanError(f"Unexpected error cleaning {target_dir}: {e}") from e


def snapshot_directory(target_dir: Path) -> FileSnapshot:
    """
    Create a snapshot of directory state with files and modification times.

    Args:
        target_dir: Directory to snapshot

    Returns:
        FileSnapshot: Snapshot of the directory state
    """
    logger.debug("Creating directory snapshot", target_dir=str(target_dir))

    # Ensure target_dir is absolute
    target_dir = target_dir.resolve()

    timestamp = datetime.now(timezone.utc)
    files = {}

    # Handle case where directory doesn't exist
    if not target_dir.exists():
        logger.debug(
            "Snapshot target directory does not exist", target_dir=str(target_dir)
        )
        return FileSnapshot(timestamp=timestamp, files=files)

    if not target_dir.is_dir():
        logger.warning("Snapshot target is not a directory", target_dir=str(target_dir))
        return FileSnapshot(timestamp=timestamp, files=files)

    try:
        # Recursively walk the directory
        for root, dirs, filenames in os.walk(target_dir):
            root_path = Path(root)

            # Process files
            for filename in filenames:
                file_path = root_path / filename
                try:
                    # Get relative path from target_dir
                    relative_path = file_path.relative_to(target_dir)

                    # Get modification time
                    mtime = file_path.stat().st_mtime

                    # Store with forward slashes for consistency
                    files[str(relative_path).replace("\\", "/")] = mtime

                except (OSError, ValueError) as e:
                    logger.warning(
                        "Failed to get file info during snapshot",
                        file=str(file_path),
                        error=str(e),
                    )
                    continue

        logger.info(
            "Directory snapshot created",
            target_dir=str(target_dir),
            file_count=len(files),
        )

        return FileSnapshot(timestamp=timestamp, files=files)

    except Exception as e:
        logger.error(
            "Failed to create directory snapshot",
            target_dir=str(target_dir),
            error=str(e),
        )
        # Return empty snapshot rather than failing
        return FileSnapshot(timestamp=timestamp, files={})


def compute_written_files(before: FileSnapshot, after: FileSnapshot) -> List[str]:
    """
    Compute new or modified files between snapshots, applying ignore patterns.

    Args:
        before: Snapshot taken before the operation
        after: Snapshot taken after the operation

    Returns:
        List of relative file paths that were written (new or modified)
    """
    logger.debug(
        "Computing written files",
        before_count=len(before.files),
        after_count=len(after.files),
    )

    written_files = []

    # Check each file in the after snapshot
    for file_path, after_mtime in after.files.items():
        # Skip if file matches ignore patterns
        if _should_ignore_file(file_path):
            logger.debug("Ignoring file due to patterns", file=file_path)
            continue

        before_mtime = before.files.get(file_path)

        # File is new or modified
        if before_mtime is None or after_mtime != before_mtime:
            written_files.append(file_path)
            logger.debug(
                "File was written",
                file=file_path,
                before_mtime=before_mtime,
                after_mtime=after_mtime,
            )

    # Sort for deterministic output
    written_files.sort()

    logger.info("Computed written files", total_written=len(written_files))

    return written_files


def ensure_directory_exists(path: Path) -> None:
    """
    Create directory if it doesn't exist, including parent directories.

    Args:
        path: Directory path to create

    Raises:
        CleanError: If directory creation fails
    """
    logger.debug("Ensuring directory exists", path=str(path))

    # Ensure path is absolute
    path = path.resolve()

    if path.exists():
        if not path.is_dir():
            raise CleanError(f"Path exists but is not a directory: {path}")
        logger.debug("Directory already exists", path=str(path))
        return

    try:
        path.mkdir(parents=True, exist_ok=True)
        logger.info("Directory created", path=str(path))

    except (OSError, PermissionError) as e:
        logger.error("Failed to create directory", path=str(path), error=str(e))
        raise CleanError(f"Failed to create directory {path}: {e}") from e


def _should_ignore_file(file_path: str) -> bool:
    """
    Check if a file should be ignored based on patterns and extensions.

    Args:
        file_path: Relative file path to check

    Returns:
        True if file should be ignored
    """
    path = Path(file_path)

    # Check file extension
    if path.suffix in IGNORE_EXTENSIONS:
        return True

    # Check if any part of the path matches ignore patterns
    for part in path.parts:
        if part in IGNORE_PATTERNS:
            return True

    return False

