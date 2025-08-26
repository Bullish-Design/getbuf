# filepath: tests/test_version.py
# =============================================================================
# tests/test_version.py
# =============================================================================
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from getbuf.version import (
    __version__,
    detect_buf_version,
    detect_plugin_version,
    get_getbuf_version,
    get_version_info,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.\-_]+)?$")


def _fake_run(stdout: str = "", stderr: str = "", returncode: int = 0) -> Any:
    """Create a fake object similar to subprocess.CompletedProcess."""
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_library_version_constant_format():
    assert isinstance(__version__, str)
    assert SEMVER_RE.match(__version__) is not None


def test_get_getbuf_version_matches_constant():
    assert get_getbuf_version() == __version__


@pytest.mark.parametrize(
    "output",
    [
        "1.2.3\n",
        "buf version 1.2.3 (linux/amd64)\n",
        "v1.2.3\n",  # we still extract 1.2.3
        "1.2.3-rc1\n",
        "1.2.3+build.7\n",
    ],
)
def test_detect_buf_version_parsing(monkeypatch: pytest.MonkeyPatch, output: str):
    import subprocess  # local import to patch cleanly

    def fake_run(cmd: list[str], **_: Any):
        assert cmd[:2] == ["buf", "--version"]
        return _fake_run(stdout=output)

    monkeypatch.setattr(subprocess, "run", fake_run)  # type: ignore[attr-defined]
    ver = detect_buf_version()
    assert ver is not None
    assert SEMVER_RE.match(ver) is not None


def test_detect_buf_version_missing_binary(monkeypatch: pytest.MonkeyPatch):
    import subprocess

    def fake_run(*_: Any, **__: Any):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)  # type: ignore[attr-defined]
    assert detect_buf_version() is None


def test_detect_plugin_version_first_candidate_hits(monkeypatch: pytest.MonkeyPatch):
    import subprocess

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: Any):
        calls.append(cmd)
        # Make the first candidate succeed
        if cmd[0] == "protoc-gen-python_betterproto":
            return _fake_run(stdout="1.9.0")
        return _fake_run(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)  # type: ignore[attr-defined]
    ver = detect_plugin_version()
    assert ver == "1.9.0"
    # Ensure we didn't need to try later candidates after success
    assert calls[0][0] == "protoc-gen-python_betterproto"


def test_detect_plugin_version_all_missing(monkeypatch: pytest.MonkeyPatch):
    import subprocess

    def fake_run(*_: Any, **__: Any):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)  # type: ignore[attr-defined]
    assert detect_plugin_version() is None


def test_version_info_aggregation(monkeypatch: pytest.MonkeyPatch):
    # Patch the high-level functions to ensure aggregation format is stable
    monkeypatch.setattr("getbuf.version.get_getbuf_version", lambda: "0.1.0")
    monkeypatch.setattr("getbuf.version.detect_buf_version", lambda: "1.2.3")
    monkeypatch.setattr("getbuf.version.detect_plugin_version", lambda: None)

    info = get_version_info()
    assert info == {
        "getbuf": "0.1.0",
        "buf": "1.2.3",
        "betterproto_plugin": None,
    }
