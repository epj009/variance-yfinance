"""
Professional logging configuration for Variance.

Provides:
- Rotating file handlers
- Multiple log files (app, error, audit, API)
- Structured logging with context
- Per-module log level control
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.getenv("VARIANCE_LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

_session_context = threading.local()


class ContextFilter(logging.Filter):
    """Add session ID and other context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = getattr(_session_context, "session_id", "N/A")
        record.duration_ms = getattr(_session_context, "duration_ms", None)
        return True


class FlushingTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """TimedRotatingFileHandler that flushes after every write for real-time logging."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record and immediately flush to disk."""
        super().emit(record)
        self.flush()


class ColoredFormatter(logging.Formatter):
    """Colored console output for development."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "line": record.lineno,
            "message": record.getMessage(),
            "session_id": getattr(record, "session_id", None),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        return json.dumps(log_data)


def setup_logging(
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    *,
    enable_debug_file: bool = False,
    json_format: bool = False,
) -> None:
    """
    Configure application-wide logging.

    Args:
        console_level: Console output level (DEBUG, INFO, WARNING, ERROR)
        file_level: File output level (DEBUG, INFO, WARNING, ERROR)
        enable_debug_file: Whether to create separate debug log file
        json_format: Use JSON format for file logs
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    if os.getenv("VARIANCE_NO_COLOR"):
        console_formatter = logging.Formatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        console_formatter = ColoredFormatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    app_handler = FlushingTimedRotatingFileHandler(
        LOG_DIR / "variance.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    app_handler.suffix = "%Y-%m-%d"
    if json_format:
        app_handler.setFormatter(JSONFormatter())
    else:
        app_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
        app_handler.setFormatter(logging.Formatter(app_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
    app_handler.addFilter(ContextFilter())
    root_logger.addHandler(app_handler)

    error_handler = FlushingTimedRotatingFileHandler(
        LOG_DIR / "variance-error.log",
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.suffix = "%Y-%m-%d"
    error_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s\n%(exc_info)s"
    error_handler.setFormatter(logging.Formatter(error_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
    error_handler.addFilter(ContextFilter())
    root_logger.addHandler(error_handler)

    audit_handler = FlushingTimedRotatingFileHandler(
        LOG_DIR / "variance-audit.log",
        when="midnight",
        interval=1,
        backupCount=365,
        encoding="utf-8",
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.suffix = "%Y-%m-%d"
    audit_format = "%(asctime)s | %(message)s"
    audit_handler.setFormatter(logging.Formatter(audit_format, datefmt="%Y-%m-%d %H:%M:%S"))
    audit_handler.addFilter(ContextFilter())

    audit_logger = logging.getLogger("variance.audit")
    audit_logger.handlers.clear()
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False

    api_handler = FlushingTimedRotatingFileHandler(
        LOG_DIR / "variance-api.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    api_handler.setLevel(logging.DEBUG)
    api_handler.suffix = "%Y-%m-%d"
    api_format = "%(asctime)s | %(name)s:%(lineno)d | %(message)s"
    api_handler.setFormatter(logging.Formatter(api_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
    api_handler.addFilter(ContextFilter())

    api_logger = logging.getLogger("variance.tastytrade_client")
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.DEBUG)

    screening_handler = FlushingTimedRotatingFileHandler(
        LOG_DIR / "variance-screening.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    screening_handler.setLevel(logging.INFO)
    screening_handler.suffix = "%Y-%m-%d"
    screening_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    screening_handler.setFormatter(
        logging.Formatter(screening_format, datefmt="%Y-%m-%d %H:%M:%S.%f")
    )
    screening_handler.addFilter(ContextFilter())

    screening_logger = logging.getLogger("variance.screening.steps")
    screening_logger.addHandler(screening_handler)
    screening_logger.setLevel(logging.INFO)

    if enable_debug_file:
        debug_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "variance-debug.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_format = (
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        )
        debug_handler.setFormatter(logging.Formatter(debug_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
        debug_handler.addFilter(ContextFilter())
        root_logger.addHandler(debug_handler)

    logging.getLogger("variance.screening").setLevel(logging.INFO)
    logging.getLogger("variance.market_data").setLevel(logging.INFO)
    logging.getLogger("variance.tastytrade_client").setLevel(logging.INFO)
    logging.getLogger("variance.models").setLevel(logging.WARNING)
    logging.getLogger("variance.diagnostics").setLevel(logging.INFO)
    logging.getLogger("variance.signals").setLevel(logging.INFO)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    root_logger.info(
        "Logging configured",
        extra={"console_level": console_level, "file_level": file_level},
    )


def set_session_id(session_id: str) -> None:
    """Set session ID for current thread."""
    _session_context.session_id = session_id


def get_session_id() -> str | None:
    """Get session ID for current thread."""
    return getattr(_session_context, "session_id", None)


def generate_session_id() -> str:
    """Generate unique session ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    import uuid

    short_uuid = str(uuid.uuid4())[:8]
    return f"sess_{timestamp}_{short_uuid}"


def audit_log(message: str, **context: Any) -> None:
    """
    Write to audit log.

    Example:
        audit_log("Screening completed", profile="balanced", symbols=50, candidates=5)
    """
    logger = logging.getLogger("variance.audit")
    context_str = " | ".join(f"{k}={v}" for k, v in context.items())
    full_message = f"{message} | {context_str}" if context else message
    logger.info(full_message)
