"""Test Pydantic models for GetBuf data structures."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from getbuf.models import (
    BufGenSpec,
    CleanError,
    CleanOperation,
    ExecutionError,
    FileSnapshot,
    GenerationResult,
    GetBufConfig,
    GetBufError,
    PluginSpec,
    ValidationError,
)


class TestExceptionHierarchy:
    """Test custom exception classes."""

    def test_exception_hierarchy(self):
        """Test that exceptions inherit correctly."""
        assert issubclass(ValidationError, GetBufError)
        assert issubclass(ExecutionError, GetBufError)
        assert issubclass(CleanError, GetBufError)
        assert issubclass(GetBufError, Exception)

    def test_exceptions_can_be_raised(self):
        """Test that all exceptions can be raised with messages."""
        with pytest.raises(GetBufError):
            raise GetBufError("Base error")

        with pytest.raises(ValidationError):
            raise ValidationError("Validation failed")

        with pytest.raises(ExecutionError):
            raise ExecutionError("Execution failed")

        with pytest.raises(CleanError):
            raise CleanError("Clean failed")


class TestGenerationResult:
    """Test GenerationResult model."""

    def test_generation_result_creation(self):
        """Test creating a GenerationResult with all fields."""
        result = GenerationResult(
            success=True,
            exit_code=0,
            command=["buf", "generate", "--template", "buf.gen.yaml"],
            workdir="/test/dir",
            duration_s=1.25,
            stdout="Generated successfully",
            stderr="",
            out_dirs=["./src/proto"],
            cleaned_dirs=[],
            written_files=["src/proto/example.py"],
        )

        assert result.success is True
        assert result.exit_code == 0
        assert result.command == ["buf", "generate", "--template", "buf.gen.yaml"]
        assert result.workdir == "/test/dir"
        assert result.duration_s == 1.25
        assert result.out_dirs == ["./src/proto"]
        assert result.written_files == ["src/proto/example.py"]

    def test_generation_result_with_optional_fields(self):
        """Test GenerationResult with optional fields set."""
        result = GenerationResult(
            success=False,
            exit_code=1,
            command=["buf", "generate"],
            workdir="/test",
            duration_s=0.5,
            stdout="",
            stderr="Error occurred",
            out_dirs=["./out"],
            cleaned_dirs=["./out"],
            written_files=[],
            logs_path="/tmp/getbuf.log",
            buf_version="1.44.0",
            plugin_version="2.0.0",
            env_subset={"BUF_CACHE_DIR": ".cache"},
        )

        assert result.logs_path == "/tmp/getbuf.log"
        assert result.buf_version == "1.44.0"
        assert result.plugin_version == "2.0.0"
        assert result.env_subset == {"BUF_CACHE_DIR": ".cache"}

    def test_generation_result_immutable(self):
        """Test that GenerationResult is frozen/immutable."""
        result = GenerationResult(
            success=True,
            exit_code=0,
            command=["buf"],
            workdir="/test",
            duration_s=1.0,
            stdout="",
            stderr="",
            out_dirs=[],
            cleaned_dirs=[],
            written_files=[],
        )

        with pytest.raises(ValueError, match="frozen"):
            result.success = False

    def test_generation_result_json_serialization(self):
        """Test JSON serialization of GenerationResult."""
        result = GenerationResult(
            success=True,
            exit_code=0,
            command=["buf", "generate"],
            workdir="/test",
            duration_s=1.5,
            stdout="output",
            stderr="",
            out_dirs=["./src"],
            cleaned_dirs=[],
            written_files=["src/test.py"],
        )

        json_str = result.model_dump_json()
        data = json.loads(json_str)

        assert data["success"] is True
        assert data["exit_code"] == 0
        assert data["command"] == ["buf", "generate"]
        assert data["duration_s"] == 1.5


class TestPluginSpec:
    """Test PluginSpec model."""

    def test_valid_plugin_name(self):
        """Test valid plugin with name kind."""
        plugin = PluginSpec(kind="name", value="python_betterproto")
        assert plugin.kind == "name"
        assert plugin.value == "python_betterproto"

    def test_valid_plugin_reference(self):
        """Test valid plugin with plugin kind."""
        plugin = PluginSpec(kind="plugin", value="python-betterproto")
        assert plugin.kind == "plugin"
        assert plugin.value == "python-betterproto"

    def test_invalid_kind(self):
        """Test that invalid kind raises ValueError."""
        with pytest.raises(ValueError, match="Plugin kind must be"):
            PluginSpec(kind="invalid", value="python_betterproto")

    def test_invalid_plugin_value(self):
        """Test that invalid plugin values are rejected."""
        with pytest.raises(ValueError, match="Only local BetterProto plugins"):
            PluginSpec(kind="name", value="python_grpc")

    def test_remote_plugin_rejected(self):
        """Test that remote/BSR plugins are rejected."""
        with pytest.raises(ValueError, match="Remote/BSR plugin references"):
            PluginSpec(kind="name", value="buf.build/protocolbuffers/go")

        with pytest.raises(ValueError, match="Remote/BSR plugin references"):
            PluginSpec(kind="name", value="github.com/user/plugin")

    def test_plugin_spec_immutable(self):
        """Test that PluginSpec is frozen."""
        plugin = PluginSpec(kind="name", value="python_betterproto")

        with pytest.raises(ValueError, match="frozen"):
            plugin.kind = "plugin"


class TestBufGenSpec:
    """Test BufGenSpec model."""

    def test_valid_buf_gen_spec(self):
        """Test creating a valid BufGenSpec."""
        plugin = PluginSpec(kind="name", value="python_betterproto")
        spec = BufGenSpec(version="v1", plugin=plugin, out_dir=Path("./src/proto"))

        assert spec.version == "v1"
        assert spec.plugin == plugin
        assert spec.out_dir == Path("./src/proto")

    def test_invalid_version(self):
        """Test that invalid version raises ValueError."""
        plugin = PluginSpec(kind="name", value="python_betterproto")

        with pytest.raises(ValueError, match="Only version 'v1' supported"):
            BufGenSpec(version="v2", plugin=plugin, out_dir=Path("./out"))

    def test_buf_gen_spec_immutable(self):
        """Test that BufGenSpec is frozen."""
        plugin = PluginSpec(kind="name", value="python_betterproto")
        spec = BufGenSpec(version="v1", plugin=plugin, out_dir=Path("./out"))

        with pytest.raises(ValueError, match="frozen"):
            spec.version = "v2"


class TestFileSnapshot:
    """Test FileSnapshot model."""

    def test_file_snapshot_creation(self):
        """Test creating a FileSnapshot."""
        now = datetime.now()
        snapshot = FileSnapshot(
            timestamp=now, files={"file1.py": 123456.0, "file2.py": 123457.0}
        )

        assert snapshot.timestamp == now
        assert snapshot.files == {"file1.py": 123456.0, "file2.py": 123457.0}

    def test_file_snapshot_immutable(self):
        """Test that FileSnapshot is frozen."""
        snapshot = FileSnapshot(timestamp=datetime.now(), files={})

        with pytest.raises(ValueError, match="frozen"):
            snapshot.files = {"new": 1.0}


class TestCleanOperation:
    """Test CleanOperation model."""

    def test_clean_operation_success(self):
        """Test successful clean operation."""
        operation = CleanOperation(
            target_dir=Path("./src/proto"),
            cleaned=True,
            files_removed=["old_file.py", "another.py"],
        )

        assert operation.target_dir == Path("./src/proto")
        assert operation.cleaned is True
        assert operation.files_removed == ["old_file.py", "another.py"]

    def test_clean_operation_no_op(self):
        """Test clean operation that was a no-op."""
        operation = CleanOperation(
            target_dir=Path("./nonexistent"), cleaned=False, files_removed=[]
        )

        assert operation.cleaned is False
        assert operation.files_removed == []


class TestGetBufConfig:
    """Test GetBufConfig model."""

    def test_valid_config_creation(self):
        """Test creating a valid GetBufConfig."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create required files
            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_path = temp_path / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            config = GetBufConfig(
                source_dir=source_dir, buf_gen_path=buf_gen_path, clean=True
            )

            assert config.source_dir.is_absolute()
            assert config.buf_gen_path.is_absolute()
            assert config.clean is True

    def test_source_dir_missing_buf_yaml(self):
        """Test that missing buf.yaml raises error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            # No buf.yaml created

            buf_gen_path = temp_path / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            with pytest.raises(ValueError, match="must contain buf.yaml"):
                GetBufConfig(source_dir=source_dir, buf_gen_path=buf_gen_path)

    def test_nonexistent_source_dir(self):
        """Test that nonexistent source_dir raises error."""
        with pytest.raises(ValueError, match="Path does not exist"):
            GetBufConfig(
                source_dir=Path("/nonexistent"), buf_gen_path=Path("/also/nonexistent")
            )

    def test_nonexistent_buf_gen_path(self):
        """Test that nonexistent buf_gen_path raises error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            with pytest.raises(ValueError, match="Path does not exist"):
                GetBufConfig(
                    source_dir=source_dir,
                    buf_gen_path=Path("/nonexistent/buf.gen.yaml"),
                )

    def test_buf_gen_path_is_directory(self):
        """Test that buf_gen_path must be a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_dir = temp_path / "buf_gen_dir"
            buf_gen_dir.mkdir()

            with pytest.raises(ValueError, match="must be a file"):
                GetBufConfig(source_dir=source_dir, buf_gen_path=buf_gen_dir)

    def test_config_with_string_paths(self):
        """Test that string paths are converted to Path objects."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_path = temp_path / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            # Pass strings instead of Path objects
            config = GetBufConfig(
                source_dir=str(source_dir), buf_gen_path=str(buf_gen_path)
            )

            assert isinstance(config.source_dir, Path)
            assert isinstance(config.buf_gen_path, Path)

    def test_config_immutable(self):
        """Test that GetBufConfig is frozen."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_path = temp_path / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            config = GetBufConfig(source_dir=source_dir, buf_gen_path=buf_gen_path)

            with pytest.raises(ValueError, match="frozen"):
                config.clean = True

