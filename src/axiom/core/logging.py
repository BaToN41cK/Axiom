"""Structured logging for AXIOM — standard `logging` module, configured once.

All modules should use ``logger = logging.getLogger(__name__)`` at module level
and call the standard methods (``logger.info``, ``logger.warning``, …).

Logs are written to ``~/.axiom/logs/latest.log`` with a rotating scheme.
``DEBUG`` level is set unless the config says otherwise.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from axiom.core.config import axiom_home

#: The root AXIOM logger — all child loggers propagate to this one.
_LOG = logging.getLogger("axiom")

#: Track whether setup_logging() was called (idempotent).
_setup_done = False


def setup_logging(*, level: int | str | None = None, force: bool = False) -> None:
    """Configure AXIOM logging once.

    Args:
        level: Override the log level (default: INFO, or DEBUG if
               ``AXIOM_DEBUG`` env var is set).
        force: Reconfigure even if setup was already called.
    """
    global _setup_done
    if _setup_done and not force:
        return
    _setup_done = True

    if level is None:
        level = os.environ.get("AXIOM_DEBUG", "").lower() in ("1", "true", "yes")
        level = logging.DEBUG if level else logging.INFO

    log_dir = axiom_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "latest.log"

    _LOG.setLevel(level)

    # Remove any existing handlers to avoid duplicates on force re-setup.
    _LOG.handlers.clear()

    # --- file handler (rotating, keeps last 3 × 1 MiB) ---
    try:
        fh = logging.handlers.RotatingFileHandler(
            str(log_path), maxBytes=1_048_576, backupCount=2, encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(_format(include_location=True))
        _LOG.addHandler(fh)
    except OSError:
        pass  # Logging must never crash the application.

    # --- stderr handler (only WARNING+ in production) ---
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(_format(include_location=False))
    _LOG.addHandler(sh)

    # Suppress noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "textual"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _LOG.info("AXIOM logging initialised (level=%s, file=%s)", logging.getLevelName(level), log_path)


def _format(*, include_location: bool) -> logging.Formatter:
    if include_location:
        return logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s  %(message)s  (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    return logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    """Shortcut: ``logging.getLogger(f'axiom.{name}')``."""
    return logging.getLogger(f"axiom.{name}")
