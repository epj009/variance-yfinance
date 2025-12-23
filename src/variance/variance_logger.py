import logging
import os
import sys
from datetime import datetime

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name: str = "variance", level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a standardized logger for the Variance system.
    Logs to console (stderr) and file (logs/variance.log).
    """
    logger = logging.getLogger(name)

    # prevent adding multiple handlers if setup is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler (Stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    log_file = os.path.join(LOG_DIR, f"variance_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Singleton instance
logger = setup_logger()
