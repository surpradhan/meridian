"""
Structured Logging Configuration

Sets up centralized logging with structured output for all components.
Enables JSON logging for better log aggregation in production.
"""

import logging
import json
import sys
from typing import Any, Dict
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string with log data
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add custom fields if present
        if hasattr(record, "custom_fields"):
            log_data.update(record.custom_fields)

        # Add standard fields
        if record.funcName:
            log_data["function"] = record.funcName
        if record.lineno:
            log_data["line"] = record.lineno

        return json.dumps(log_data)


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = True,
    file_path: str = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON format (True) or text format (False)
        file_path: Optional file path for file logging
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Create formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if file_path:
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding structured fields to logs."""

    def __init__(self, **fields: Any):
        """
        Initialize log context with custom fields.

        Args:
            **fields: Key-value pairs to add to all logs in this context
        """
        self.fields = fields
        self.handlers = []

    def __enter__(self):
        """Enter context and apply fields to all handlers."""
        # Add custom fields to all handlers
        for handler in logging.root.handlers:
            old_emit = handler.emit

            def emit_with_fields(record, old_emit=old_emit):
                record.custom_fields = self.fields
                return old_emit(record)

            handler.emit = emit_with_fields
            self.handlers.append((handler, old_emit))

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original handlers."""
        for handler, old_emit in self.handlers:
            handler.emit = old_emit
        return False
