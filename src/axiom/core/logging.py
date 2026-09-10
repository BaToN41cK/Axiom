"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Patterns whose values must never reach the log file.
_REDACT_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(gsk_[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?[^\"'\s,}]+)", re.IGNORECASE),
    re.compile(r"(authorization[\"']?\s*[:=]\s*[\"']?[^\"'\s,}]+)", re.IGNORECASE),
]

_REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Redact known secret patterns from a string."""
    result = text
    for pattern in _REDACT_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        except Exception:  # noqa: BLE001 - never break logging
            pass
        return True


def get_log_dir() -> Path:
    """Return the Axiom log directory (created on demand).

    Honours AXIOM_HOME override (used by tests).
    """
    import os

    home = Path(os.environ.get("AXIOM_HOME", Path.home() / ".axiom"))
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(level: int = logging.INFO, quiet_console: bool = False) -> Path:
    """Configure root logging for Axiom. Returns the log file path."""
    log_file = get_log_dir() / "axiom.log"
    root = logging.getLogger("axiom")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.propagate = False

    redactor = _RedactingFilter()

    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    if not quiet_console:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(level)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        console.addFilter(redactor)
        root.addHandler(console)
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced Axiom logger."""
    return logging.getLogger(f"axiom.{name}")


def close_logging() -> None:
    """Close all axiom log handlers (releases file locks on Windows)."""
    root = logging.getLogger("axiom")
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        root.removeHandler(handler)
