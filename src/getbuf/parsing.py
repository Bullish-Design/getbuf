"""YAML parsing and validation for buf.gen.yaml files."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict

from getbuf.logging import logger
from getbuf.models import BufGenSpec, PluginSpec, ValidationError


def parse_buf_gen_yaml(buf_gen_path: Path, source_dir: Path) -> BufGenSpec:
    """
    Parse and validate buf.gen.yaml with GetBuf constraints.

    Args:
        buf_gen_path: Path to buf.gen.yaml file
        source_dir: Source directory for resolving relative paths

    Returns:
        BufGenSpec: Validated specification

    Raises:
        ValidationError: On parsing or validation failures
    """
    logger.debug(
        "Parsing buf.gen.yaml",
        buf_gen_path=str(buf_gen_path),
        source_dir=str(source_dir),
    )

    try:
        with open(buf_gen_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ValidationError(f"buf.gen.yaml not found: {buf_gen_path}")
    except yaml.YAMLError as e:
        raise ValidationError(f"Invalid YAML in buf.gen.yaml: {e}")
    except Exception as e:
        raise ValidationError(f"Error reading buf.gen.yaml: {e}")

    if not isinstance(data, dict):
        raise ValidationError("buf.gen.yaml must contain a YAML object")

    # Validate version
    version = data.get("version")
    if version != "v1":
        raise ValidationError(f"buf.gen.yaml version must be 'v1', got: {version}")

    # Validate plugins section
    plugins = data.get("plugins")
    if plugins is None:
        raise ValidationError("buf.gen.yaml must contain 'plugins' section")

    if not isinstance(plugins, list):
        raise ValidationError("'plugins' must be a list")

    if len(plugins) != 1:
        raise ValidationError(f"Exactly one plugin required, got {len(plugins)}")

    plugin_dict = plugins[0]
    if not isinstance(plugin_dict, dict):
        raise ValidationError("Plugin entry must be an object")

    # Extract and validate plugin
    plugin_spec = extract_plugin_spec(plugin_dict)

    # Extract and validate out directory
    out = plugin_dict.get("out")
    if not out:
        raise ValidationError("Plugin must specify 'out' directory")

    # Resolve output path relative to source directory
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = (source_dir / out_path).resolve()
    else:
        out_path = out_path.resolve()

    logger.info(
        "Successfully parsed buf.gen.yaml",
        plugin_kind=plugin_spec.kind,
        plugin_value=plugin_spec.value,
        out_dir=str(out_path),
    )

    return BufGenSpec(version=version, plugin=plugin_spec, out_dir=out_path)


def validate_buf_yaml(buf_yaml_path: Path) -> None:
    """
    Ensure buf.yaml exists and is readable.

    Args:
        buf_yaml_path: Path to buf.yaml file

    Raises:
        ValidationError: If buf.yaml is missing or unreadable
    """
    logger.debug("Validating buf.yaml", path=str(buf_yaml_path))

    if not buf_yaml_path.exists():
        raise ValidationError(f"buf.yaml not found: {buf_yaml_path}")

    if not buf_yaml_path.is_file():
        raise ValidationError(f"buf.yaml must be a file: {buf_yaml_path}")

    try:
        with open(buf_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValidationError(f"Invalid YAML in buf.yaml: {e}")
    except Exception as e:
        raise ValidationError(f"Error reading buf.yaml: {e}")

    if not isinstance(data, dict):
        raise ValidationError("buf.yaml must contain a YAML object")

    logger.debug("buf.yaml validation passed")


def extract_plugin_spec(plugin_dict: Dict[str, Any]) -> PluginSpec:
    """
    Extract and validate plugin specification.

    Args:
        plugin_dict: Plugin configuration dictionary

    Returns:
        PluginSpec: Validated plugin specification

    Raises:
        ValidationError: On invalid plugin configuration
    """
    logger.debug("Extracting plugin spec", plugin_dict=plugin_dict)

    # Check for plugin reference type
    name = plugin_dict.get("name")
    plugin = plugin_dict.get("plugin")

    if name and plugin:
        raise ValidationError(
            "Plugin entry cannot have both 'name' and 'plugin' fields"
        )

    if not name and not plugin:
        raise ValidationError("Plugin entry must have either 'name' or 'plugin' field")

    if name:
        kind = "name"
        value = name
    else:
        kind = "plugin"
        value = plugin

    if not isinstance(value, str):
        raise ValidationError(f"Plugin {kind} must be a string")

    # PluginSpec validation will handle BetterProto/remote validation
    try:
        plugin_spec = PluginSpec(kind=kind, value=value)
    except ValueError as e:
        raise ValidationError(f"Invalid plugin specification: {e}")

    logger.debug(
        "Plugin spec extracted successfully",
        kind=plugin_spec.kind,
        value=plugin_spec.value,
    )

    return plugin_spec

