# src/tests/test_core.py
"""Test core GetBuf functionality."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from getbuf.core import GetBuf
from getbuf.models import ExecutionError, GenerationResult, ValidationError


class TestGetBufInit:
    """Test GetBuf initialization."""

    def test_successful_initialization(self):
        """Test successful GetBuf initialization with valid inputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create source directory with buf.yaml
            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            # Create buf.gen.yaml
            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            # Should initialize successfully
            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            assert getbuf._config.source_dir == source_dir.resolve()
            assert getbuf._config.buf_gen_path == buf_gen_path.resolve()
            assert getbuf._buf_gen_spec.version == "v1"
            assert getbuf._buf_gen_spec.plugin.value == "python_betterproto2"

    def test_invalid_source_directory(self):
        """Test initialization with invalid source directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_dir = Path(temp_dir) / "nonexistent"
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            with pytest.raises(ValidationError, match="Invalid configuration"):
                GetBuf(source_dir=nonexistent_dir, buf_gen_path=buf_gen_path)

    def test_missing_buf_yaml(self):
        """Test initialization when buf.yaml is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create source directory without buf.yaml
            source_dir = temp_path / "source"
            source_dir.mkdir()

            buf_gen_path = temp_path / "buf.gen.yaml"
            buf_gen_path.write_text("version: v1")

            with pytest.raises(ValidationError, match="Invalid configuration"):
                GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

    def test_invalid_buf_gen_yaml(self):
        """Test initialization with invalid buf.gen.yaml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            # Create invalid buf.gen.yaml
            buf_gen_content = {
                "version": "v1",
                "plugins": [],  # Empty plugins list
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            with pytest.raises(ValidationError):
                GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)


class TestGetBufRun:
    """Test GetBuf run workflow."""

    def _create_test_setup(self, temp_dir: Path):
        """Helper to create test setup with valid files."""
        source_dir = temp_dir / "source"
        source_dir.mkdir()
        (source_dir / "buf.yaml").write_text("version: v1")

        buf_gen_content = {
            "version": "v1",
            "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
        }
        buf_gen_path = temp_dir / "buf.gen.yaml"
        with open(buf_gen_path, "w") as f:
            yaml.dump(buf_gen_content, f)

        return source_dir, buf_gen_path

    @patch("getbuf.core.subprocess.run")
    def test_successful_run(self, mock_subprocess):
        """Test successful complete workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir, buf_gen_path = self._create_test_setup(temp_path)

            # Create output directory
            output_dir = source_dir / "generated"
            output_dir.mkdir()

            # Mock subprocess.run for buf generate
            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="Generation successful", stderr=""
            )

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Mock telemetry methods
            with (
                patch.object(getbuf, "_get_buf_version", return_value="1.44.0"),
                patch.object(getbuf, "_get_plugin_version", return_value="2.0.0"),
                patch.object(
                    getbuf, "_get_env_subset", return_value={"BUF_CACHE": ".cache"}
                ),
            ):
                result = getbuf.run(clean=False)

            assert isinstance(result, GenerationResult)
            assert result.success is True
            assert result.exit_code == 0
            assert result.command == [
                "buf",
                "generate",
                "--template",
                str(buf_gen_path),
            ]
            assert result.workdir == str(source_dir)
            assert result.duration_s > 0
            assert result.stdout == "Generation successful"
            assert result.stderr == ""
            assert result.out_dirs == [str(output_dir)]
            assert result.cleaned_dirs == []
            assert result.buf_version == "1.44.0"
            assert result.plugin_version == "2.0.0"
            assert result.env_subset == {"BUF_CACHE": ".cache"}

            # Verify subprocess was called correctly
            mock_subprocess.assert_called_once_with(
                ["buf", "generate", "--template", str(buf_gen_path)],
                cwd=source_dir,
                capture_output=True,
                text=True,
                check=False,
            )

    @patch("getbuf.core.subprocess.run")
    def test_successful_run_with_cleaning(self, mock_subprocess):
        """Test successful workflow with cleaning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir, buf_gen_path = self._create_test_setup(temp_path)

            # Create output directory with existing files
            output_dir = source_dir / "generated"
            output_dir.mkdir()
            (output_dir / "old_file.py").write_text("old content")

            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="Generation successful", stderr=""
            )

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            with (
                patch.object(getbuf, "_get_buf_version", return_value=None),
                patch.object(getbuf, "_get_plugin_version", return_value=None),
                patch.object(getbuf, "_get_env_subset", return_value={}),
            ):
                result = getbuf.run(clean=True)

            assert result.success is True
            assert result.cleaned_dirs == [str(output_dir)]
            # Old file should be removed
            assert not (output_dir / "old_file.py").exists()

    @patch("getbuf.core.subprocess.run")
    def test_buf_generation_failure(self, mock_subprocess):
        """Test handling of buf generate failure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir, buf_gen_path = self._create_test_setup(temp_path)

            # Mock failed subprocess
            mock_subprocess.return_value = MagicMock(
                returncode=1, stdout="", stderr="buf: error parsing proto files"
            )

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            with (
                patch.object(getbuf, "_get_buf_version", return_value=None),
                patch.object(getbuf, "_get_plugin_version", return_value=None),
                patch.object(getbuf, "_get_env_subset", return_value={}),
            ):
                result = getbuf.run()

            assert result.success is False
            assert result.exit_code == 1
            assert result.stderr == "buf: error parsing proto files"

    @patch("getbuf.core.subprocess.run")
    def test_buf_binary_not_found(self, mock_subprocess):
        """Test handling when buf binary is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir, buf_gen_path = self._create_test_setup(temp_path)

            # Mock FileNotFoundError for missing buf binary
            mock_subprocess.side_effect = FileNotFoundError("buf not found")

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)
            result = getbuf.run()

            assert result.success is False
            assert result.exit_code == 127
            assert "buf binary not found" in result.stderr

    def test_validation_error_handling(self):
        """Test handling of validation errors during run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir, buf_gen_path = self._create_test_setup(temp_path)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Mock validation to fail
            with patch.object(
                getbuf,
                "_validate_inputs",
                side_effect=ValidationError("Test validation error"),
            ):
                result = getbuf.run()

            assert result.success is False
            assert result.exit_code == 2
            assert "[validation] Test validation error" in result.stderr


class TestGetBufValidation:
    """Test GetBuf validation methods."""

    def test_validate_inputs_success(self):
        """Test successful input validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Should not raise
            getbuf._validate_inputs()

    def test_validate_inputs_missing_buf_yaml(self):
        """Test validation failure when buf.yaml is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()

            # Create buf.yaml first, then remove it to simulate missing file
            buf_yaml = source_dir / "buf.yaml"
            buf_yaml.write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Remove buf.yaml after initialization to test validation
            buf_yaml.unlink()

            with pytest.raises(ValidationError):
                getbuf._validate_inputs()


class TestGetBufCleaning:
    """Test GetBuf cleaning functionality."""

    def test_clean_if_requested_skip_when_false(self):
        """Test that cleaning is skipped when clean=False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            cleaned_dirs = getbuf._clean_if_requested(clean=False)

            assert cleaned_dirs == []

    def test_clean_if_requested_performs_cleaning(self):
        """Test that cleaning is performed when clean=True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            # Create output directory with files
            output_dir = source_dir / "generated"
            output_dir.mkdir()
            (output_dir / "old_file.py").write_text("old content")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            cleaned_dirs = getbuf._clean_if_requested(clean=True)

            assert cleaned_dirs == [str(output_dir)]
            assert not (output_dir / "old_file.py").exists()
            assert output_dir.exists()  # Directory itself should remain


class TestGetBufExecution:
    """Test GetBuf subprocess execution."""

    @patch("getbuf.core.subprocess.run")
    def test_execute_buf_generate_success(self, mock_subprocess):
        """Test successful buf generate execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="Generated successfully", stderr=""
            )

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)
            command, exit_code, stdout, stderr = getbuf._execute_buf_generate()

            assert command == ["buf", "generate", "--template", str(buf_gen_path)]
            assert exit_code == 0
            assert stdout == "Generated successfully"
            assert stderr == ""

            mock_subprocess.assert_called_once_with(
                ["buf", "generate", "--template", str(buf_gen_path)],
                cwd=source_dir,
                capture_output=True,
                text=True,
                check=False,
            )

    @patch("getbuf.core.subprocess.run")
    def test_execute_buf_generate_not_found(self, mock_subprocess):
        """Test handling when buf binary is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            mock_subprocess.side_effect = FileNotFoundError("buf not found")

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            with pytest.raises(ExecutionError, match="buf binary not found"):
                getbuf._execute_buf_generate()


class TestGetBufTelemetry:
    """Test GetBuf telemetry gathering."""

    @patch("getbuf.core.subprocess.run")
    def test_gather_telemetry_success(self, mock_subprocess):
        """Test successful telemetry gathering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Mock version calls
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="1.44.0"),  # buf --version
                MagicMock(returncode=0, stdout="2.0.0"),  # plugin --version
            ]

            with patch.dict("os.environ", {"BUF_CACHE_DIR": ".cache"}):
                buf_version, plugin_version, env_subset = getbuf._gather_telemetry()

            assert buf_version == "1.44.0"
            assert plugin_version == "2.0.0"
            assert env_subset == {"BUF_CACHE_DIR": ".cache"}

    @patch("getbuf.core.subprocess.run")
    def test_gather_telemetry_version_failures(self, mock_subprocess):
        """Test telemetry gathering when version calls fail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            source_dir = temp_path / "source"
            source_dir.mkdir()
            (source_dir / "buf.yaml").write_text("version: v1")

            buf_gen_content = {
                "version": "v1",
                "plugins": [{"name": "python_betterproto2", "out": "./generated"}],
            }
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, "w") as f:
                yaml.dump(buf_gen_content, f)

            getbuf = GetBuf(source_dir=source_dir, buf_gen_path=buf_gen_path)

            # Mock version calls to fail
            mock_subprocess.side_effect = FileNotFoundError("Not found")

            buf_version, plugin_version, env_subset = getbuf._gather_telemetry()

            assert buf_version is None
            assert plugin_version is None
            assert isinstance(env_subset, dict)
