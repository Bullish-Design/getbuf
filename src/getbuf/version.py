# filepath: src/getbuf/version.py
# =============================================================================
# src/getbuf/version.py
# =============================================================================
from __future__ import annotations

import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Library version (bumped via release workflow)
__version__ = "0.1.0"

# A simple SemVer-ish matcher: 1.2.3, optionally with suffixes like -rc1 or +meta
_VERSION_RE = re.compile(r"(?P<ver>\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.\-_]+)?)")


def get_getbuf_version() -> str:
    """Return the installed getbuf library version."""
    return __version__


def _run_and_parse_version(cmd: list[str], timeout: float = 2.0) -> Optional[str]:
    """
    Run a command and extract the first SemVer-ish token from its output.

    Returns:
        The version string if found, else None. Any failure is treated as non-fatal.
    """
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.debug("Binary not found for command: %s", cmd)
        return None
    except subprocess.TimeoutExpired:
        logger.debug("Timed out while running command: %s", cmd)
        return None
    except Exception as exc:  # Defensive: never raise from version probes
        logger.debug("Unexpected error running %s: %s", cmd, exc)
        return None

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = _VERSION_RE.search(out.strip())
    if not match:
        logger.debug("No version pattern found in output for %s: %r", cmd, out)
        return None
    return match.group("ver")


def detect_buf_version() -> str | None:
    """Best-effort `buf --version` detection."""
    return _run_and_parse_version(["buf", "--version"])


def detect_plugin_version() -> str | None:
    """
    Best-effort detection of the BetterProto v2 plugin version.

    We try a few likely binary names, returning on the first match.
    """
    candidates: list[list[str]] = [
        ["protoc-gen-python_betterproto", "--version"],
        ["protoc-gen-python-betterproto", "--version"],
        ["python_betterproto", "--version"],
        ["python-betterproto", "--version"],
    ]
    for cmd in candidates:
        ver = _run_and_parse_version(cmd)
        if ver:
            return ver
    return None


def get_version_info() -> dict[str, str | None]:
    """Collect and return all relevant version info."""
    return {
        "getbuf": get_getbuf_version(),
        "buf": detect_buf_version(),
        "betterproto_plugin": detect_plugin_version(),
    }
