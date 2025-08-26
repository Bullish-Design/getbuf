# filepath: src/getbuf/cli.py
# =============================================================================
# src/getbuf/cli.py
# =============================================================================
from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any, Optional

import typer

# Library imports expected by the prompt
# - Keep imports narrow to avoid import-time side effects
from getbuf.core import GetBuf
from getbuf.models import GetBufError
from getbuf import logging as gb_logging

# NOTE: We intentionally avoid importing the actual Pydantic model type at
# type-check time to prevent import cycles during CLI import in some setups.
try:  # pragma: no cover - defensive import
    from getbuf.models import GenerationResult  # type: ignore
except Exception:  # pragma: no cover
    GenerationResult = Any  # type: ignore[misc,assignment]

app = typer.Typer(no_args_is_help=False, add_completion=False)


def _enable_verbose_logging(verbose: bool) -> None:
    """
    Ensure library logging honors the CLI --verbose flag before any work runs.

    We call into getbuf.logging to configure things centrally. If the library
    does not expose a configure function yet, fall back to a sane default.
    """
    try:
        # Preferred: let the library own its logging shape.
        if hasattr(gb_logging, "configure_logging"):
            gb_logging.configure_logging(debug=verbose)  # type: ignore[attr-defined]
        elif hasattr(gb_logging, "enable_debug_logging"):
            gb_logging.enable_debug_logging(verbose)  # type: ignore[attr-defined]
        else:  # pragma: no cover
            import logging

            logging.basicConfig(
                level=logging.DEBUG if verbose else logging.INFO,
                format="%(levelname)s %(name)s: %(message)s",
            )
    except Exception:  # pragma: no cover - never crash on logging setup
        pass


def _print_json_result(result: Any) -> None:
    """
    Print the GenerationResult as JSON to stdout.

    We try the library's Pydantic v2 API first (model_dump_json). If not
    available, we fall back to a plain json.dumps on __dict__ or as-is.
    """
    try:
        # Pydantic v2 models
        text = result.model_dump_json(by_alias=True, exclude_none=True)  # type: ignore[attr-defined]
        print(text)
        return
    except Exception:
        pass

    try:
        # Pydantic v2 fallback: let Pydantic handle serialization
        data = result.model_dump(by_alias=True, exclude_none=True)  # type: ignore[attr-defined]
        print(json.dumps(data))
        return
    except Exception:
        pass

    # Last resorts
    try:
        print(json.dumps(result))  # type: ignore[arg-type]
    except TypeError:
        print(json.dumps(getattr(result, "__dict__", {"result": str(result)})))


def _buf_version() -> Optional[str]:
    """
    Best-effort detection of the buf CLI version.
    Not fatal if not available.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["buf", "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        txt = (out.stdout or "").strip()
        return txt or None
    except Exception:  # pragma: no cover
        return None


@app.command()
def gen(
    source_dir: str = typer.Argument(
        ..., help="Path to local Buf module containing buf.yaml"
    ),
    buf_gen: str = typer.Argument(..., help="Path to user-supplied buf.gen.yaml"),
    clean: bool = typer.Option(
        False, "--clean", help="Clean the output directory before generation"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Emit JSON GenerationResult to stdout"
    ),
) -> None:
    """Generate stubs using buf."""
    _enable_verbose_logging(verbose)

    # Basic CLI validation
    source_path = Path(source_dir)
    buf_gen_path = Path(buf_gen)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(
            f"ERROR: source_dir does not exist or is not a directory: {source_dir}",
            err=True,
        )
        raise typer.Exit(code=2)
    if not buf_gen_path.exists() or not buf_gen_path.is_file():
        typer.echo(
            f"ERROR: buf_gen does not exist or is not a file: {buf_gen}", err=True
        )
        raise typer.Exit(code=2)

    try:
        runner = GetBuf()
        result: GenerationResult = runner.run(
            source_dir=str(source_path),
            buf_gen_path=str(buf_gen_path),
            clean=clean,
        )

        if json_output:
            _print_json_result(result)
            raise typer.Exit(code=int(getattr(result, "exit_code", 1)))

        # Human-friendly output (concise)
        exit_code = int(getattr(result, "exit_code", 1))
        success = bool(getattr(result, "success", False))
        message = getattr(result, "message", None)

        if not success:
            if message:
                typer.echo(f"Generation failed: {message}", err=True)
            raise typer.Exit(code=exit_code)

        # On success, print a brief line; detailed info belongs in JSON mode
        typer.echo("Generation succeeded.")
        raise typer.Exit(code=exit_code)

    except GetBufError as e:
        # Library-defined error surface
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def clean(
    source_dir: str = typer.Argument(
        ..., help="Path to local Buf module containing buf.yaml"
    ),
    buf_gen: str = typer.Argument(
        ..., help="Path to user-supplied buf.gen.yaml (used to locate out dir)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
) -> None:
    """Clean output directory only."""
    _enable_verbose_logging(verbose)

    source_path = Path(source_dir)
    buf_gen_path = Path(buf_gen)
    if not source_path.exists() or not source_path.is_dir():
        typer.echo(
            f"ERROR: source_dir does not exist or is not a directory: {source_dir}",
            err=True,
        )
        raise typer.Exit(code=2)
    if not buf_gen_path.exists() or not buf_gen_path.is_file():
        typer.echo(
            f"ERROR: buf_gen does not exist or is not a file: {buf_gen}", err=True
        )
        raise typer.Exit(code=2)

    try:
        runner = GetBuf()
        # By contract in this step, `clean=True` means "ignore generation".
        result: GenerationResult = runner.run(
            source_dir=str(source_path),
            buf_gen_path=str(buf_gen_path),
            clean=True,
        )

        exit_code = int(getattr(result, "exit_code", 0))
        success = bool(getattr(result, "success", True))
        message = getattr(result, "message", None)

        if not success:
            if message:
                typer.echo(f"Clean failed: {message}", err=True)
            raise typer.Exit(code=exit_code)

        typer.echo("Clean succeeded.")
        raise typer.Exit(code=0)

    except GetBufError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def fetch() -> None:
    """Placeholder - prints help and exits non-zero."""
    # As per prompt, just show the top-level help and exit non-zero.
    # This keeps the command wired in for future steps.
    typer.echo(app.get_help())
    raise typer.Exit(code=2)


@app.callback(invoke_without_command=True)
def version_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", help="Show GetBuf and tool versions"
    ),
) -> None:
    """Print version info."""
    if not version:
        # If no subcommand was provided, show help and exit 0 to match typical UX.
        if ctx.invoked_subcommand is None:
            typer.echo(app.get_help())
            raise typer.Exit(code=0)
        return

    # Compose a compact, helpful version report
    lines = []
    try:
        lines.append(f"getbuf: {pkg_version('getbuf')}")
    except PackageNotFoundError:
        lines.append("getbuf: (package metadata not found)")

    try:
        lines.append(f"typer: {pkg_version('typer')}")
    except PackageNotFoundError:
        pass

    try:
        import pydantic  # type: ignore

        lines.append(f"pydantic: {getattr(pydantic, '__version__', 'unknown')}")
    except Exception:
        pass

    buf_ver = _buf_version()
    if buf_ver:
        lines.append(f"buf: {buf_ver}")

    typer.echo("\n".join(lines))
    raise typer.Exit(code=0)


def main() -> None:
    """Main entry point for console_scripts."""
    app()
