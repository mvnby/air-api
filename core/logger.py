import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Create logs directory if it doesn't exist
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

def setup_logging(session_log_file: str = None, clear_session_log: bool = False):
    """
    Configures the root logger with:
    1. RotatingFileHandler for robust file logging.
    2. StreamHandler for console output (dev).
    """
    # Create config for Root Logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clean previous handlers to avoid duplication if called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    # Determine log file path
    if session_log_file:
        log_path = Path(__file__).parent.parent / session_log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if clear_session_log and log_path.exists():
            log_path.unlink()
    else:
        log_path = LOG_FILE

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 1. File Handler (Rotating)
    # Max size 10MB, keep 5 backups
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    return logger

# Singleton instance access if needed, though getLogger() usage is preferred
logger = setup_logging()
