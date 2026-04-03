"""
logger.py — DevMind's Logging System
Structured logging with file + console handlers.
Replaces scattered print() calls with proper DEBUG/INFO/WARNING/ERROR levels.
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(
    name: str = "devmind",
    level: str | None = None,
    log_to_file: bool = True,
) -> logging.Logger:
    """
    Configure and return the DevMind logger.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var or INFO.
        log_to_file: Whether to also write logs to ~/.devmind/logs/

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if already configured
    if logger.handlers:
        return logger

    # Determine log level
    if level is None:
        env_level = os.getenv("DEVMIND_LOG_LEVEL", "INFO").upper()
        level = env_level

    logger.setLevel(getattr(logging, level, logging.INFO))

    # Console handler — only WARNING and above (avoids cluttering the terminal)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # File handler — logs everything for debugging
    if log_to_file:
        try:
            log_dir = Path.home() / ".devmind" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / f"devmind_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_fmt = logging.Formatter(
                "%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s",
                datefmt="%H:%M:%S",
            )
            file_handler.setFormatter(file_fmt)
            logger.addHandler(file_handler)
        except Exception:
            # If file logging fails, console logging is still available
            pass

    return logger


# Default logger — import this across all modules
log = setup_logger()
