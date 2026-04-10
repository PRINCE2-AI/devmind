"""
logger.py — DevMind's Logging System
Structured logging with file + console handlers.

Features:
  - Rotating log files (no unbounded growth)
  - Secret masking (API keys, tokens, passwords redacted automatically)
  - Optional JSON structured logs for machine parsing
  - Per-module child loggers via get_logger(name)
"""

import json
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path
from datetime import datetime


# Secret masking patterns
_SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(api[_\-]?key|apikey|token|password|secret)\s*[:=]\s*['\"]?[^\s'\"&]{8,}"),
     r"\1=***REDACTED***"),
    (re.compile(r"(?i)authorization\s*[:=]\s*['\"]?[^\s'\"&]+"),
     "authorization=***REDACTED***"),
]


def mask_secrets(text):
    """Redact common secret patterns from a string."""
    if not text or not isinstance(text, str):
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretMaskingFilter(logging.Filter):
    """Logging filter that redacts secrets from log records."""

    def filter(self, record):
        try:
            if isinstance(record.msg, str):
                record.msg = mask_secrets(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        mask_secrets(a) if isinstance(a, str) else a
                        for a in record.args
                    )
                elif isinstance(record.args, dict):
                    record.args = {
                        k: (mask_secrets(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
        except Exception:
            pass
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON."""

    def format(self, record):
        payload = {
            "time": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logger(name="devmind", level=None, log_to_file=True, json_logs=None):
    """Configure and return the DevMind logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    if level is None:
        level = os.getenv("DEVMIND_LOG_LEVEL", "INFO").upper()

    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False
    logger.addFilter(SecretMaskingFilter())

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    console_handler.addFilter(SecretMaskingFilter())
    logger.addHandler(console_handler)

    if log_to_file:
        try:
            log_dir = Path.home() / ".devmind" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"devmind_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            if json_logs is None:
                json_logs = os.getenv("DEVMIND_LOG_JSON", "").lower() == "true"
            if json_logs:
                file_handler.setFormatter(JsonFormatter())
            else:
                file_handler.setFormatter(logging.Formatter(
                    "%(asctime)s | %(name)-18s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S",
                ))
            file_handler.addFilter(SecretMaskingFilter())
            logger.addHandler(file_handler)
        except Exception:
            pass

    return logger


def get_logger(name):
    """Return a child logger under the root devmind logger."""
    setup_logger()
    return logging.getLogger(f"devmind.{name}")


log = setup_logger()
