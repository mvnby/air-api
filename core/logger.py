import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from .config import settings

# Global flag to track if logging has been set up
_logging_configured = False

def setup_logging(session_log_file=None, clear_session_log=False):
    """
    Setup logging with support for both cumulative and session-based logs.
    Uses a singleton pattern to prevent duplicate handlers.
    
    Args:
        session_log_file: Optional path to a session-specific log file (e.g., server.log, bot.log)
        clear_session_log: If True, clears the session log file on startup
    """
    global _logging_configured
    
    # If already configured in this process, just return the logger
    if _logging_configured:
        return logging.getLogger()
    
    # Ensure logs directory exists
    log_dir = os.path.dirname(settings.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Base configuration
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)
    
    # Cumulative file handler with rotation (app.log)
    # This keeps full history with automatic rotation
    cumulative_handler = RotatingFileHandler(
        settings.LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    cumulative_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(cumulative_handler)
    
    # Session-specific file handler (server.log or bot.log)
    # This is cleared on each restart for easy debugging
    if session_log_file:
        # Clear the session log if requested
        if clear_session_log and os.path.exists(session_log_file):
            open(session_log_file, 'w').close()
        
        session_handler = logging.FileHandler(session_log_file, mode='a')
        session_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(session_handler)
    
    # Mark as configured
    _logging_configured = True
    
    return logger

# Export a default logger instance for backward compatibility
# This will be replaced when setup_logging() is called in main.py or bot_app/main.py
logger = logging.getLogger()
