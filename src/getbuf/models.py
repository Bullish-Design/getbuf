"""Pydantic models for GetBuf data structures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Exception Hierarchy
# =============================================================================


class GetBufError(Exception):
    """Base exception for unrecoverable library errors."""

    pass


class ValidationError(GetBufError):
    """Raised on YAML parse errors or invariant violations."""

    pass


class ExecutionError(GetBufError):
    """Raised if subprocess invocation cannot be started."""

    pass


class CleanError(GetBufError):
    """Raised on unexpected FS failures during cleaning."""

    pass


# =============================================================================
# Core Data Models
# =============================================================================


class GenerationResult(BaseModel):
    """
    Immutable result object describing a GetBuf generation run.

    Contains telemetry, file changes, and execution details for
    deterministic CI/tooling pipelines.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool = Field(description="True if validation passed and Buf exited 0")
    exit_code: int = Field(description="Underlying process exit code")
    command: List[str] = Field(description="Exact argv for Buf (reproducibility)")
    workdir: str = Field(description="Directory where Buf was executed")
    duration_s: float = Field(description="Wall-clock time in seconds")
    stdout: str = Field(description="Captured standard output")
    stderr: str = Field(
        description="Captured standard error including validation messages"
    )
    logs_path: Optional[str] = Field(
        default=None, description="Temp .log path for long output"
    )
    out_dirs: List[str] = Field(description="Output directories from buf.gen.yaml")
    cleaned_dirs: List[str] = Field(
        description="Dirs whose contents were removed via clean=True"
    )
    written_files: List[str] = Field(
        description="Files added/changed in out after the run"
    )
    buf_version: Optional[str] = Field(
        default=None, description="Best-effort buf --version output"
    )
    plugin_version: Optional[str] = Field(
        default=None, description="Best-effort protoc-gen-python_betterproto version"
    )
    env_subset: Dict[str, str] = Field(
        default_factory=dict, description="Snapshot of relevant environment variables"
    )


class PluginSpec(BaseModel):
    """
    Represents a plugin configuration from buf.gen.yaml.

    Enforces that only local BetterProto v2 plugins are accepted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(description="Plugin reference type ('name' or 'plugin')")
    value: str = Field(description="Plugin identifier (must be local BetterProto)")

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        """Ensure kind is either 'name' or 'plugin'."""
        if v not in {"name", "plugin"}:
            raise ValueError(f"Plugin kind must be 'name' or 'plugin', got: {v}")
        return v

    @field_validator("value")
    @classmethod
    def validate_betterproto(cls, v: str) -> str:
        """Ensure plugin represents local BetterProto v2."""
        # First check for BSR/remote references
        if "/" in v or v.startswith("buf.build"):
            raise ValueError(f"Remote/BSR plugin references not supported: {v}")

        # Then check if it's a valid local BetterProto plugin
        valid_plugins = {
            "python_betterproto",
            "python-betterproto",
            "python_betterproto2",
            "python-betterproto2",
        }
        if v not in valid_plugins:
            raise ValueError(
                f"Only local BetterProto plugins supported: {valid_plugins}, got: {v}"
            )
        return v


class BufGenSpec(BaseModel):
    """
    Represents the structure of a buf.gen.yaml file.

    Enforces exactly one local BetterProto v2 plugin and one output dir.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(description="buf.gen.yaml version (must be 'v1')")
    plugin: PluginSpec = Field(description="Single plugin specification")
    out_dir: Path = Field(description="Normalized output directory path")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Ensure version is v1."""
        if v != "v1":
            raise ValueError(f"Only version 'v1' supported, got: {v}")
        return v


class FileSnapshot(BaseModel):
    """
    Represents a snapshot of files in a directory for change detection.

    Maps file paths to their modification times for diff operations.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime = Field(description="When this snapshot was taken")
    files: Dict[str, float] = Field(description="Map of file path to modification time")


class CleanOperation(BaseModel):
    """
    Represents the result of a directory cleaning operation.

    Records what was cleaned for telemetry and verification.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_dir: Path = Field(description="Directory that was targeted for cleaning")
    cleaned: bool = Field(description="Whether cleaning was actually performed")
    files_removed: List[str] = Field(description="List of files that were removed")


class GetBufConfig(BaseModel):
    """
    Main configuration object for GetBuf operations.

    Encapsulates source directory, buf.gen.yaml path, and options.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_dir: Path = Field(
        description="Directory containing buf.yaml (normalized absolute path)"
    )
    buf_gen_path: Path = Field(
        description="Path to buf.gen.yaml file (normalized absolute path)"
    )
    clean: bool = Field(
        default=False,
        description="Whether to clean output directories before generation",
    )

    @field_validator("source_dir", "buf_gen_path")
    @classmethod
    def validate_path_exists(cls, v: Path) -> Path:
        """Ensure paths exist and are normalized to absolute."""
        if isinstance(v, str):
            v = Path(v)

        # Normalize to absolute path
        abs_path = v.resolve()

        if not abs_path.exists():
            raise ValueError(f"Path does not exist: {abs_path}")

        return abs_path

    @field_validator("source_dir")
    @classmethod
    def validate_source_dir_has_buf_yaml(cls, v: Path) -> Path:
        """Ensure source_dir contains buf.yaml."""
        buf_yaml = v / "buf.yaml"
        if not buf_yaml.exists():
            raise ValueError(f"source_dir must contain buf.yaml: {v}")
        return v

    @field_validator("buf_gen_path")
    @classmethod
    def validate_buf_gen_is_file(cls, v: Path) -> Path:
        """Ensure buf_gen_path is a file."""
        if not v.is_file():
            raise ValueError(f"buf_gen_path must be a file: {v}")
        return v

