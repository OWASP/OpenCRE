"""OpenCRE structured JSON logging.

This package is intentionally standalone: importing it must not import
``application`` or Flask. Application modules should use::

    from cre_logging import get_logger

    logger = get_logger(__name__)

Each line on stderr is one JSON object with ``level``, ``message``,
``module``, ``file`` (repo-relative path), and ``method`` (calling
function). ``LOG_LEVEL`` selects the root level (default ``INFO``).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

_HANDLER_NAME = "cre-json"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESERVED_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "asctime",
    "message",
}


class _CurrentStderr:
    """Follow the live ``sys.stderr`` so tests can redirect it."""

    def write(self, data: str) -> int:
        return sys.stderr.write(data)

    def flush(self) -> None:
        sys.stderr.flush()


class JSONFormatter(logging.Formatter):
    """Format a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "file": _relative_file(record.pathname),
            "method": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str, ensure_ascii=False)


def _relative_file(pathname: str) -> str:
    if not pathname:
        return ""
    try:
        return str(Path(pathname).resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return Path(pathname).name


def _level_from_env() -> int:
    name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return int(getattr(logging, name, logging.INFO))


def configure_logging(force: bool = False) -> None:
    """Install a single JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(_level_from_env())
    existing = [
        handler
        for handler in root.handlers
        if getattr(handler, "name", "") == _HANDLER_NAME
    ]
    if existing and not force:
        for handler in existing:
            handler.setFormatter(JSONFormatter())
        return
    for handler in existing:
        root.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(_CurrentStderr())
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    logging.captureWarnings(True)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger; first call configures JSON output."""
    configure_logging()
    return logging.getLogger(name if name else "opencre")


configure_logging()
