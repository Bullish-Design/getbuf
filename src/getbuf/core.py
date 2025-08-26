# src/getbuf/core.py
"""Core GetBuf functionality and orchestration."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from getbuf.fs import (
    clean_directory_contents,
    compute_written_files,
    ensure_directory_exists,
    snapshot_directory,
)
from getbuf.logging import logger
from getbuf.models import (
    BufGenSpec,
    ExecutionError,
    GenerationResult,
    GetBufConfig,
    ValidationError,
)
from getbuf.parsing import parse_buf_gen_yaml, validate_buf_yaml


class GetBuf:
    """
    Main orchestration class for GetBuf operations.

    Coordinates validation, optional cleaning, buf execution,
    and result assembly with rich telemetry.
    """

    def __init__(self, source_dir: str | Path, buf_gen_path: str | Path) -> None:
        """
        Initialize GetBuf with source directory and buf.gen.yaml path.

        Args:
            source_dir: Directory containing buf.yaml
            buf_gen_path: Path to buf.gen.yaml configuration file

        Raises:
            ValidationError: If paths are invalid or missing required files
        """
        logger.debug(
            "Initializing GetBuf",
            source_dir=str(source_dir),
            buf_gen_path=str(buf_gen_path),
        )

        try:
            self._config = GetBufConfig(
                source_dir=Path(source_dir),
                buf_gen_path=Path(buf_gen_path),
            )
        except ValueError as e:
            logger.error("Configuration validation failed", error=str(e))
            raise ValidationError(f"Invalid configuration: {e}") from e

        # Parse buf.gen.yaml during initialization
        try:
            self._buf_gen_spec = parse_buf_gen_yaml(
                self._config.buf_gen_path, self._config.source_dir
            )
        except ValidationError:
            logger.error("buf.gen.yaml validation failed")
            raise

        logger.info(
            "GetBuf initialized successfully",
            source_dir=str(self._config.source_dir),
            out_dir=str(self._buf_gen_spec.out_dir),
        )

    def run(self, clean: bool = False) -> GenerationResult:
        """
        Execute the complete GetBuf workflow.

        Args:
            clean: Whether to clean output directories before generation

        Returns:
            GenerationResult: Complete execution results and telemetry
        """
        logger.info("Starting GetBuf run", clean=clean)
        start_time = time.time()

        try:
            # Step 1: Validate all inputs
            self._validate_inputs()

            # Step 2: Clean output directories if requested
            cleaned_dirs = self._clean_if_requested(clean)

            # Step 3: Take snapshot before generation
            before_snapshot = snapshot_directory(self._buf_gen_spec.out_dir)

            # Step 4: Execute buf generate
            command, exit_code, stdout, stderr = self._execute_buf_generate()

            # Step 5: Take snapshot after generation and compute diff
            after_snapshot = snapshot_directory(self._buf_gen_spec.out_dir)
            written_files = compute_written_files(before_snapshot, after_snapshot)

            # Step 6: Gather telemetry
            buf_version, plugin_version, env_subset = self._gather_telemetry()

            # Calculate duration
            duration_s = time.time() - start_time

            # Determine success
            success = exit_code == 0

            logger.info(
                "GetBuf run completed",
                success=success,
                exit_code=exit_code,
                duration_s=duration_s,
                written_files=len(written_files),
            )

            return GenerationResult(
                success=success,
                exit_code=exit_code,
                command=command,
                workdir=str(self._config.source_dir),
                duration_s=duration_s,
                stdout=stdout,
                stderr=stderr,
                out_dirs=[str(self._buf_gen_spec.out_dir)],
                cleaned_dirs=cleaned_dirs,
                written_files=written_files,
                buf_version=buf_version,
                plugin_version=plugin_version,
                env_subset=env_subset,
            )

        except ValidationError as e:
            # Return failed result for validation errors
            duration_s = time.time() - start_time
            logger.error("Validation failed", error=str(e))

            return GenerationResult(
                success=False,
                exit_code=2,
                command=[],
                workdir=str(self._config.source_dir),
                duration_s=duration_s,
                stdout="",
                stderr=f"[validation] {str(e)}",
                out_dirs=[str(self._buf_gen_spec.out_dir)],
                cleaned_dirs=[],
                written_files=[],
            )

        except ExecutionError as e:
            # Return failed result for execution errors
            duration_s = time.time() - start_time
            logger.error("Execution failed", error=str(e))

            return GenerationResult(
                success=False,
                exit_code=127,  # Command not found
                command=[],
                workdir=str(self._config.source_dir),
                duration_s=duration_s,
                stdout="",
                stderr=f"[execution] {str(e)}",
                out_dirs=[str(self._buf_gen_spec.out_dir)],
                cleaned_dirs=[],
                written_files=[],
            )

        except Exception as e:
            # Unexpected errors
            duration_s = time.time() - start_time
            logger.error("Unexpected error in GetBuf run", error=str(e))

            return GenerationResult(
                success=False,
                exit_code=1,
                command=[],
                workdir=str(self._config.source_dir),
                duration_s=duration_s,
                stdout="",
                stderr=f"[unexpected] {str(e)}",
                out_dirs=[str(self._buf_gen_spec.out_dir)],
                cleaned_dirs=[],
                written_files=[],
            )

    def _validate_inputs(self) -> None:
        """
        Validate all required inputs before proceeding.

        Raises:
            ValidationError: If validation fails
        """
        logger.debug("Validating inputs")

        # Validate buf.yaml exists (already checked in GetBufConfig)
        buf_yaml_path = self._config.source_dir / "buf.yaml"
        validate_buf_yaml(buf_yaml_path)

        # buf.gen.yaml validation already done in __init__
        logger.debug("Input validation passed")

    def _clean_if_requested(self, clean: bool) -> List[str]:
        """
        Clean output directories if requested.

        Args:
            clean: Whether to perform cleaning

        Returns:
            List of directories that were cleaned

        Raises:
            ValidationError: If cleaning fails
        """
        cleaned_dirs = []

        if not clean:
            logger.debug("Cleaning not requested, skipping")
            return cleaned_dirs

        logger.info("Cleaning output directory", target=str(self._buf_gen_spec.out_dir))

        try:
            # Ensure the output directory exists
            ensure_directory_exists(self._buf_gen_spec.out_dir)

            # Clean the directory contents
            clean_operation = clean_directory_contents(self._buf_gen_spec.out_dir)

            if clean_operation.cleaned:
                cleaned_dirs.append(str(self._buf_gen_spec.out_dir))

            logger.info(
                "Directory cleaning completed",
                cleaned=clean_operation.cleaned,
                files_removed=len(clean_operation.files_removed),
            )

        except Exception as e:
            logger.error("Directory cleaning failed", error=str(e))
            raise ValidationError(f"Failed to clean directory: {e}") from e

        return cleaned_dirs

    def _execute_buf_generate(self) -> tuple[List[str], int, str, str]:
        """
        Execute buf generate command with telemetry.

        Returns:
            Tuple of (command, exit_code, stdout, stderr)

        Raises:
            ExecutionError: If buf binary cannot be found or started
        """
        # Construct command
        command = [
            "buf",
            "generate",
            "--template",
            str(self._config.buf_gen_path),
        ]

        logger.info(
            "Executing buf generate",
            command=command,
            workdir=str(self._config.source_dir),
        )

        try:
            # Ensure output directory exists before generation
            ensure_directory_exists(self._buf_gen_spec.out_dir)

            # Execute the command
            result = subprocess.run(
                command,
                cwd=self._config.source_dir,
                capture_output=True,
                text=True,
                check=False,  # Don't raise on non-zero exit
            )

            logger.info(
                "buf generate completed",
                exit_code=result.returncode,
                stdout_length=len(result.stdout),
                stderr_length=len(result.stderr),
            )

            return command, result.returncode, result.stdout, result.stderr

        except FileNotFoundError as e:
            logger.error("buf binary not found", error=str(e))
            raise ExecutionError(
                "buf binary not found on PATH. Please ensure buf is installed."
            ) from e

        except Exception as e:
            logger.error("Failed to execute buf generate", error=str(e))
            raise ExecutionError(f"Failed to execute buf generate: {e}") from e

    def _gather_telemetry(self) -> tuple[Optional[str], Optional[str], Dict[str, str]]:
        """
        Gather telemetry data including versions and environment.

        Returns:
            Tuple of (buf_version, plugin_version, env_subset)
        """
        logger.debug("Gathering telemetry")

        # Gather buf version (best effort)
        buf_version = self._get_buf_version()

        # Gather plugin version (best effort)
        plugin_version = self._get_plugin_version()

        # Gather environment subset
        env_subset = self._get_env_subset()

        logger.debug(
            "Telemetry gathered",
            buf_version=buf_version,
            plugin_version=plugin_version,
            env_keys=list(env_subset.keys()),
        )

        return buf_version, plugin_version, env_subset

    def _get_buf_version(self) -> Optional[str]:
        """Get buf version via best-effort subprocess call."""
        try:
            result = subprocess.run(
                ["buf", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                # Extract version from output (e.g., "1.44.0")
                version = result.stdout.strip()
                logger.debug("buf version detected", version=version)
                return version
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug("Failed to get buf version", error=str(e))

        return None

    def _get_plugin_version(self) -> Optional[str]:
        """Get BetterProto plugin version via best-effort subprocess call."""
        try:
            result = subprocess.run(
                ["protoc-gen-python_betterproto", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.debug("plugin version detected", version=version)
                return version
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug("Failed to get plugin version", error=str(e))

        return None

    def _get_env_subset(self) -> Dict[str, str]:
        """Get relevant environment variables for telemetry."""
        env_subset = {}

        # Capture BUF_* environment variables
        for key, value in os.environ.items():
            if key.startswith("BUF_"):
                env_subset[key] = value

        logger.debug("Environment subset captured", keys=list(env_subset.keys()))
        return env_subset

