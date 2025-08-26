# filepath: tests/test_cli.py
# =============================================================================
# tests/test_cli.py
# =============================================================================
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from typer.testing import CliRunner

# Import the application under test
from getbuf.cli import app

runner = CliRunner()  # mix_stderr=False)


class DummyResult:
    def __init__(
        self, success: bool = True, exit_code: int = 0, message: str | None = None
    ):
        self.success = success
        self.exit_code = exit_code
        self.message = message

    # Pydantic v2-compatible method the CLI will prefer if available
    def model_dump_json(self, **_: Any) -> str:
        return json.dumps(
            {
                "success": self.success,
                "exit_code": self.exit_code,
                "message": self.message,
            }
        )


def _touch_files(tmp_path: Path) -> tuple[str, str]:
    # Create plausible paths for CLI validation
    src = tmp_path / "module"
    src.mkdir(parents=True, exist_ok=True)
    (src / "buf.yaml").write_text("version: v1\n")
    buf_gen = tmp_path / "buf.gen.yaml"
    buf_gen.write_text(
        "version: v1\nplugins:\n  - name: python_betterproto\n    out: gen\n"
    )
    return str(src), str(buf_gen)


def test_gen_happy_path(monkeypatch, tmp_path: Path) -> None:
    source_dir, buf_gen = _touch_files(tmp_path)

    # Patch the exact symbol used by the CLI module
    import getbuf.cli as cli  # type: ignore

    class DummyGetBuf:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, *args, **kwargs) -> DummyResult:
            return DummyResult(success=True, exit_code=0)

    monkeypatch.setattr(cli, "GetBuf", DummyGetBuf, raising=True)

    result = runner.invoke(app, ["gen", source_dir, buf_gen])
    assert result.exit_code == 0
    assert "Generation succeeded." in result.output


def test_gen_json_output(monkeypatch, tmp_path: Path) -> None:
    source_dir, buf_gen = _touch_files(tmp_path)

    import getbuf.cli as cli  # type: ignore

    class DummyGetBuf:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, *args, **kwargs) -> DummyResult:
            return DummyResult(success=True, exit_code=0)

    monkeypatch.setattr(cli, "GetBuf", DummyGetBuf, raising=True)

    result = runner.invoke(app, ["gen", source_dir, buf_gen, "--json"])
    assert result.exit_code == 0
    # Ensure it's JSON and contains exit_code
    payload = json.loads(result.output.strip())
    assert payload["exit_code"] == 0
    assert payload["success"] is True


def test_gen_invalid_paths(tmp_path: Path) -> None:
    # Both invalid -> should return validation exit code 2
    result = runner.invoke(
        app, ["gen", str(tmp_path / "nope"), str(tmp_path / "also-nope")]
    )
    assert result.exit_code == 2
    assert "ERROR: source_dir" in result.output


def test_clean_happy_path(monkeypatch, tmp_path: Path) -> None:
    source_dir, buf_gen = _touch_files(tmp_path)

    import getbuf.cli as cli  # type: ignore

    class DummyGetBuf:
        def __init__(self, *args, **kwargs) -> None:
            self.called = False

        def run(self, *args, **kwargs) -> DummyResult:
            self.called = True
            # Simulate success on clean
            return DummyResult(success=True, exit_code=0)

    dummy = DummyGetBuf()
    # Replace the constructor with one that returns our prebuilt instance
    monkeypatch.setattr(cli, "GetBuf", lambda *a, **k: dummy, raising=True)

    result = runner.invoke(app, ["clean", source_dir, buf_gen])
    assert result.exit_code == 0
    assert "Clean succeeded." in result.output
    assert dummy.called is True


def test_fetch_is_placeholder() -> None:
    result = runner.invoke(app, ["fetch"])
    # Placeholder should still be a non-zero exit
    assert result.exit_code != 0
    # Help text may or may not be printed depending on implementation; don't assert it strictly


def test_version_flag(monkeypatch) -> None:
    # Monkeypatch importlib.metadata.version to ensure deterministic output for getbuf only.
    from importlib import metadata as importlib_metadata

    real_version = importlib_metadata.version

    def fake_version(name: str) -> str:
        if name == "getbuf":
            return "0.1.0"
        # Defer to the actual environment for other packages like typer/pydantic
        return real_version(name)

    monkeypatch.setattr(importlib_metadata, "version", fake_version, raising=True)

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "getbuf: 0.1.0" in result.output
    # Be flexible about typer version
    assert "typer: " in result.output


def test_getbuf_error_surface(monkeypatch, tmp_path: Path) -> None:
    source_dir, buf_gen = _touch_files(tmp_path)

    import getbuf.cli as cli  # type: ignore

    # The CLI catches whatever error class it imported; mirror that.
    # If the CLI doesn't export the error type, fall back to models.
    try:
        ErrType = cli.GetBufError  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - fallback path
        from getbuf import models as _models  # type: ignore

        ErrType = _models.GetBufError  # type: ignore[attr-defined]

    class Boom(ErrType):  # type: ignore[misc]
        pass

    class DummyGetBuf:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, *args, **kwargs):
            raise Boom("kaboom")

    monkeypatch.setattr(cli, "GetBuf", DummyGetBuf, raising=True)

    result = runner.invoke(app, ["gen", source_dir, buf_gen])
    assert result.exit_code == 1
    # Output can go to stderr or stdout depending on Click; use combined output
    assert "ERROR: kaboom" in result.output
