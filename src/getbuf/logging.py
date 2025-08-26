"""Logging foundation for GetBuf with JSONL output."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class LogEntry(BaseModel):
    """Structured log entry for JSONL output."""
    
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of log entry"
    )
    level: str = Field(description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    message: str = Field(description="Primary log message")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context data"
    )
    
    @field_validator('level')
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Ensure log level is uppercase and valid."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        level = v.upper()
        if level not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return level


class JSONLHandler(logging.Handler):
    """Custom logging handler that writes structured JSONL to file."""
    
    def __init__(self, log_dir: Path):
        """Initialize JSONL handler.
        
        Args:
            log_dir: Directory to write log files
        """
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = log_dir / f"getbuf_{timestamp}.jsonl"
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as JSONL."""
        try:
            # Extract context from record extras
            context = {}
            if hasattr(record, 'context'):
                context.update(record.context)
            
            # Add any extra fields from the record
            for key, value in record.__dict__.items():
                if key not in {'name', 'msg', 'args', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'lineno', 
                              'funcName', 'created', 'msecs', 'relativeCreated',
                              'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info',
                              'context'}:
                    context[key] = value
            
            # Create structured log entry
            log_entry = LogEntry(
                level=record.levelname,
                message=record.getMessage(),
                context=context
            )
            
            # Write JSONL line
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry.model_dump_json() + '\n')
                
        except Exception:
            # Fallback to stderr if JSONL writing fails
            sys.stderr.write(f"Logging error: {record.getMessage()}\n")


class GetBufLogger:
    """GetBuf's structured logger with JSONL output."""
    
    def __init__(self, name: str = "getbuf"):
        """Initialize GetBuf logger.
        
        Args:
            name: Logger name
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)
        
        # Get log directory from environment
        log_dir_str = os.environ.get('GETBUF_LOG_DIR', './logs')
        log_dir = Path(log_dir_str)
        
        # Add JSONL handler
        jsonl_handler = JSONLHandler(log_dir)
        jsonl_handler.setLevel(logging.DEBUG)
        self._logger.addHandler(jsonl_handler)
        
        # Add console handler for immediate feedback
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self._logger.addHandler(console_handler)
    
    def debug(self, message: str, **context: Any) -> None:
        """Log debug message with optional context."""
        self._logger.debug(message, extra={'context': context})
    
    def info(self, message: str, **context: Any) -> None:
        """Log info message with optional context."""
        self._logger.info(message, extra={'context': context})
    
    def warning(self, message: str, **context: Any) -> None:
        """Log warning message with optional context."""
        self._logger.warning(message, extra={'context': context})
    
    def error(self, message: str, **context: Any) -> None:
        """Log error message with optional context."""
        self._logger.error(message, extra={'context': context})
    
    def critical(self, message: str, **context: Any) -> None:
        """Log critical message with optional context."""
        self._logger.critical(message, extra={'context': context})


# Module-level logger instance
logger = GetBufLogger()