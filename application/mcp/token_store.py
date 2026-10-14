"""Local storage for the MCP refresh token.

OS keyring when one is usable, otherwise a 0600 file. Never writes to stdout:
that stream carries JSON-RPC when the stdio server is running.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import pathlib
import time
from typing import Any, Optional

SERVICE_NAME = "opencre-mcp"
ACCOUNT_NAME = "refresh_token"

DEFAULT_TOKEN_FILE = pathlib.Path.home() / ".config" / "opencre-mcp" / "tokens.json"


def token_file() -> pathlib.Path:
    override = os.environ.get("OPENCRE_MCP_TOKEN_FILE")
    return pathlib.Path(override) if override else DEFAULT_TOKEN_FILE


def _keyring() -> Optional[Any]:
    """Return a working keyring module, or None to use the file backend."""
    if os.environ.get("OPENCRE_MCP_TOKEN_FILE"):
        return None
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
        if backend is None or "fail" in type(backend).__name__.lower():
            return None
    except Exception:
        logger.debug("keyring unavailable, using file backend", exc_info=True)
        return None
    return keyring


def save(refresh_token: str) -> None:
    ring = _keyring()
    if ring is not None:
        try:
            ring.set_password(SERVICE_NAME, ACCOUNT_NAME, refresh_token)
            return
        except Exception:
            logger.debug("keyring write failed, using file backend", exc_info=True)

    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"refresh_token": refresh_token, "saved_at": time.time()})
    # Create/truncate with mode 0600 up front — never write under a looser umask
    # and chmod afterwards. Fail closed if confidentiality cannot be guaranteed.
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
    except OSError as exc:
        raise OSError(f"cannot create confidential token file {path}") from exc
    try:
        os.fchmod(fd, 0o600)
    except (AttributeError, OSError) as exc:
        os.close(fd)
        raise OSError(f"cannot set confidential mode on token file {path}") from exc
    with os.fdopen(fd, "w") as handle:
        handle.write(payload)


def load() -> Optional[str]:
    ring = _keyring()
    if ring is not None:
        try:
            stored = ring.get_password(SERVICE_NAME, ACCOUNT_NAME)
            if stored:
                return stored
        except Exception:
            logger.debug("keyring read failed, using file backend", exc_info=True)

    path = token_file()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("refresh_token") or None
    except (ValueError, OSError):
        logger.debug("token file unreadable", exc_info=True)
        return None


def clear() -> bool:
    """Remove the stored token. True if anything was removed."""
    removed = False

    ring = _keyring()
    if ring is not None:
        try:
            if ring.get_password(SERVICE_NAME, ACCOUNT_NAME):
                ring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
                removed = True
        except Exception:
            logger.debug("keyring delete failed", exc_info=True)

    path = token_file()
    if path.exists():
        path.unlink()
        removed = True
    return removed
