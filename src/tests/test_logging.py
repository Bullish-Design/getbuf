"""Test logging functionality for GetBuf."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from getbuf.logging import LogEntry, logger


class TestLogEntry:
    """Test LogEntry Pydantic model."""
    
    def test_log_entry_creation(self):
        """Test creating a LogEntry with valid data."""
        entry = LogEntry(
            level="INFO",
            message="Test message",
            context={"key": "value"}
        )
        
        assert entry.level == "INFO"
        assert entry.message == "Test message"
        assert entry.context == {"key": "value"}
        assert entry.timestamp is not None
    
    def test_log_entry_level_validation(self):
        """Test log level validation."""
        # Valid levels should work
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            entry = LogEntry(level=level, message="test")
            assert entry.level == level
        
        # Lowercase should be converted to uppercase
        entry = LogEntry(level="info", message="test")
        assert entry.level == "INFO"
        
        # Invalid levels should raise ValueError
        with pytest.raises(ValueError, match="Invalid log level"):
            LogEntry(level="INVALID", message="test")
    
    def test_log_entry_serialization(self):
        """Test LogEntry can be serialized to JSON."""
        entry = LogEntry(level="INFO", message="Test", context={"num": 42})
        json_str = entry.model_dump_json()
        
        # Should be valid JSON
        data = json.loads(json_str)
        assert data["level"] == "INFO"
        assert data["message"] == "Test"
        assert data["context"]["num"] == 42


class TestLogging:
    """Test logging system functionality."""
    
    def test_logger_writes_jsonl(self):
        """Test that logger writes JSONL files correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set custom log directory
            os.environ['GETBUF_LOG_DIR'] = temp_dir
            
            # Import logger after setting env var to use custom directory
            from getbuf.logging import GetBufLogger
            test_logger = GetBufLogger("test")
            
            # Write test log entries
            test_logger.info("Test info message", test_key="test_value")
            test_logger.error("Test error message", error_code=500)
            
            # Find the log file
            log_dir = Path(temp_dir)
            log_files = list(log_dir.glob("getbuf_*.jsonl"))
            assert len(log_files) == 1
            
            # Read and verify JSONL content
            log_file = log_files[0]
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            assert len(lines) == 2
            
            # Verify first log entry
            entry1 = json.loads(lines[0])
            assert entry1["level"] == "INFO"
            assert entry1["message"] == "Test info message"
            assert entry1["context"]["test_key"] == "test_value"
            assert "timestamp" in entry1
            
            # Verify second log entry
            entry2 = json.loads(lines[1])
            assert entry2["level"] == "ERROR"
            assert entry2["message"] == "Test error message"
            assert entry2["context"]["error_code"] == 500
    
    def test_default_log_directory(self):
        """Test default log directory creation."""
        # Clear environment variable
        if 'GETBUF_LOG_DIR' in os.environ:
            del os.environ['GETBUF_LOG_DIR']
        
        from getbuf.logging import GetBufLogger
        test_logger = GetBufLogger("test_default")
        
        # Write a log entry to trigger directory creation
        test_logger.info("Test message")
        
        # Check that ./logs directory was created
        assert Path("./logs").exists()
        assert Path("./logs").is_dir()