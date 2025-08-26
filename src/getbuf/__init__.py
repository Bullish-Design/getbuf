# src/getbuf/__init__.py
"""Main init point for the GetBuf library."""

from __future__ import annotations

from getbuf.core import GetBuf
from getbuf.models import GenerationResult

__all__ = ["GetBuf", "GenerationResult"]
