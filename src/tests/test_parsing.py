"""Test YAML parsing and validation for GetBuf."""

from __future__ import annotations

import tempfile
import yaml
from pathlib import Path

import pytest

from getbuf.models import BufGenSpec, PluginSpec, ValidationError
from getbuf.parsing import (
    parse_buf_gen_yaml,
    validate_buf_yaml, 
    extract_plugin_spec,
)


class TestValidateBufYaml:
    """Test buf.yaml validation."""
    
    def test_valid_buf_yaml(self):
        """Test validation of valid buf.yaml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            buf_yaml = Path(temp_dir) / "buf.yaml"
            buf_yaml.write_text("version: v1\n")
            
            # Should not raise
            validate_buf_yaml(buf_yaml)
    
    def test_missing_buf_yaml(self):
        """Test error when buf.yaml is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            buf_yaml = Path(temp_dir) / "nonexistent.yaml"
            
            with pytest.raises(ValidationError, match="not found"):
                validate_buf_yaml(buf_yaml)
    
    def test_buf_yaml_is_directory(self):
        """Test error when buf.yaml is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            buf_yaml = Path(temp_dir) / "buf.yaml"
            buf_yaml.mkdir()
            
            with pytest.raises(ValidationError, match="must be a file"):
                validate_buf_yaml(buf_yaml)
    
    def test_invalid_yaml_content(self):
        """Test error with invalid YAML syntax."""
        with tempfile.TemporaryDirectory() as temp_dir:
            buf_yaml = Path(temp_dir) / "buf.yaml"
            buf_yaml.write_text("invalid: yaml: content: [")
            
            with pytest.raises(ValidationError, match="Invalid YAML"):
                validate_buf_yaml(buf_yaml)
    
    def test_non_object_yaml(self):
        """Test error when YAML is not an object."""
        with tempfile.TemporaryDirectory() as temp_dir:
            buf_yaml = Path(temp_dir) / "buf.yaml"
            buf_yaml.write_text("- not an object")
            
            with pytest.raises(ValidationError, match="must contain a YAML object"):
                validate_buf_yaml(buf_yaml)


class TestExtractPluginSpec:
    """Test plugin specification extraction."""
    
    def test_valid_name_plugin(self):
        """Test valid plugin with 'name' field."""
        plugin_dict = {"name": "python_betterproto", "out": "./src"}
        spec = extract_plugin_spec(plugin_dict)
        
        assert spec.kind == "name"
        assert spec.value == "python_betterproto"
    
    def test_valid_plugin_reference(self):
        """Test valid plugin with 'plugin' field."""
        plugin_dict = {"plugin": "python-betterproto", "out": "./src"}
        spec = extract_plugin_spec(plugin_dict)
        
        assert spec.kind == "plugin"
        assert spec.value == "python-betterproto"
    
    def test_both_name_and_plugin(self):
        """Test error when both 'name' and 'plugin' are present."""
        plugin_dict = {
            "name": "python_betterproto",
            "plugin": "python-betterproto",
            "out": "./src"
        }
        
        with pytest.raises(ValidationError, match="cannot have both"):
            extract_plugin_spec(plugin_dict)
    
    def test_neither_name_nor_plugin(self):
        """Test error when neither 'name' nor 'plugin' are present."""
        plugin_dict = {"out": "./src"}
        
        with pytest.raises(ValidationError, match="must have either"):
            extract_plugin_spec(plugin_dict)
    
    def test_non_string_plugin_value(self):
        """Test error when plugin value is not a string."""
        plugin_dict = {"name": 123, "out": "./src"}
        
        with pytest.raises(ValidationError, match="must be a string"):
            extract_plugin_spec(plugin_dict)
    
    def test_invalid_plugin_type(self):
        """Test error with unsupported plugin type."""
        plugin_dict = {"name": "python_grpc", "out": "./src"}
        
        with pytest.raises(ValidationError, match="Invalid plugin specification"):
            extract_plugin_spec(plugin_dict)
    
    def test_remote_plugin_rejected(self):
        """Test rejection of remote/BSR plugin references."""
        plugin_dict = {"name": "buf.build/protocolbuffers/go", "out": "./src"}
        
        with pytest.raises(ValidationError, match="Invalid plugin specification"):
            extract_plugin_spec(plugin_dict)


class TestParseBufGenYaml:
    """Test buf.gen.yaml parsing and validation."""
    
    def test_valid_buf_gen_yaml_name(self):
        """Test parsing valid buf.gen.yaml with 'name' plugin."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {
                        "name": "python_betterproto",
                        "out": "./proto_gen"
                    }
                ]
            }
            
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            spec = parse_buf_gen_yaml(buf_gen_path, source_dir)
            
            assert spec.version == "v1"
            assert spec.plugin.kind == "name"
            assert spec.plugin.value == "python_betterproto"
            assert spec.out_dir == (source_dir / "proto_gen").resolve()
    
    def test_valid_buf_gen_yaml_plugin(self):
        """Test parsing valid buf.gen.yaml with 'plugin' reference."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {
                        "plugin": "python-betterproto",
                        "out": "/tmp/proto_gen"
                    }
                ]
            }
            
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            spec = parse_buf_gen_yaml(buf_gen_path, source_dir)
            
            assert spec.plugin.kind == "plugin"
            assert spec.plugin.value == "python-betterproto"
            assert spec.out_dir == Path("/tmp/proto_gen").resolve()
    
    def test_missing_buf_gen_yaml(self):
        """Test error when buf.gen.yaml is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            buf_gen_path = Path(temp_dir) / "nonexistent.yaml"
            
            with pytest.raises(ValidationError, match="not found"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_invalid_yaml_syntax(self):
        """Test error with invalid YAML syntax."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            buf_gen_path.write_text("invalid: yaml: [")
            
            with pytest.raises(ValidationError, match="Invalid YAML"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_non_object_yaml(self):
        """Test error when YAML root is not an object."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            buf_gen_path.write_text("- not an object")
            
            with pytest.raises(ValidationError, match="must contain a YAML object"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_invalid_version(self):
        """Test error with wrong version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v2",
                "plugins": [{"name": "python_betterproto", "out": "./out"}]
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="version must be 'v1'"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_missing_plugins(self):
        """Test error when plugins section is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {"version": "v1"}
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="must contain 'plugins'"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_plugins_not_list(self):
        """Test error when plugins is not a list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": {"name": "python_betterproto"}
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="must be a list"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_multiple_plugins(self):
        """Test error with multiple plugins."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {"name": "python_betterproto", "out": "./out1"},
                    {"name": "python_betterproto", "out": "./out2"}
                ]
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="Exactly one plugin required"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_empty_plugins_list(self):
        """Test error with empty plugins list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": []
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="Exactly one plugin required"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_plugin_not_object(self):
        """Test error when plugin entry is not an object."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": ["python_betterproto"]
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="must be an object"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_missing_out_directory(self):
        """Test error when 'out' directory is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            source_dir.mkdir()
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {"name": "python_betterproto"}
                ]
            }
            
            buf_gen_path = Path(temp_dir) / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            with pytest.raises(ValidationError, match="must specify 'out'"):
                parse_buf_gen_yaml(buf_gen_path, source_dir)
    
    def test_relative_path_resolution(self):
        """Test that relative paths are resolved against source_dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "project" / "proto"
            source_dir.mkdir(parents=True)
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {
                        "name": "python_betterproto",
                        "out": "../generated"
                    }
                ]
            }
            
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            spec = parse_buf_gen_yaml(buf_gen_path, source_dir)
            
            expected_path = (source_dir / "../generated").resolve()
            assert spec.out_dir == expected_path
    
    def test_absolute_path_preserved(self):
        """Test that absolute paths are preserved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            source_dir.mkdir()
            
            absolute_out = "/tmp/absolute_output"
            
            buf_gen_content = {
                "version": "v1",
                "plugins": [
                    {
                        "name": "python_betterproto",
                        "out": absolute_out
                    }
                ]
            }
            
            buf_gen_path = temp_path / "buf.gen.yaml"
            with open(buf_gen_path, 'w') as f:
                yaml.dump(buf_gen_content, f)
            
            spec = parse_buf_gen_yaml(buf_gen_path, source_dir)
            
            assert spec.out_dir == Path(absolute_out).resolve()