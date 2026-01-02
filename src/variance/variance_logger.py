import logging
import os

from .logging_config import setup_logging


def setup_logger(name: str = "variance", level: int = logging.INFO) -> logging.Logger:
    """
    Backwards-compatible logger setup.

    Prefer calling setup_logging from variance.logging_config in entrypoints.
    """
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        console_level = os.getenv("VARIANCE_LOG_LEVEL", "INFO")
        file_level = os.getenv("VARIANCE_FILE_LOG_LEVEL", "DEBUG")
        enable_debug = os.getenv("VARIANCE_DEBUG", "").lower() in ("1", "true", "yes")
        json_logs = os.getenv("VARIANCE_JSON_LOGS", "").lower() in ("1", "true", "yes")
        setup_logging(
            console_level=console_level,
            file_level=file_level,
            enable_debug_file=enable_debug,
            json_format=json_logs,
        )
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


logger = setup_logger()
