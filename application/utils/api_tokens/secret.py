"""Resolve or mint ``API_TOKEN_JWT_SECRET`` (install / .env)."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_KEY = "API_TOKEN_JWT_SECRET"
_FILE_ENV = "API_TOKEN_JWT_SECRET_FILE"
_DEFAULT_FILE = "/code/.secrets/api_token_jwt_secret"


def secret_file_path() -> Path:
    return Path(os.environ.get(_FILE_ENV) or _DEFAULT_FILE)


def _is_production_config() -> bool:
    return (os.environ.get("FLASK_CONFIG") or "").strip().lower() == "production"


def ensure_api_token_jwt_secret() -> str:
    """Return the HS256 signing secret; mint+persist once if unset.

    Order: env ``API_TOKEN_JWT_SECRET`` → secret file → mint and write file.

    Under ``FLASK_CONFIG=production``, refusing an in-memory-only secret: the
    value must come from env or a successfully persisted secret file (staging
    secrets volume / explicit config). Multi-replica dynos cannot share an
    ephemeral process mint.
    """
    existing = (os.environ.get(_ENV_KEY) or "").strip()
    if existing:
        return existing

    path = secret_file_path()
    try:
        if path.is_file():
            loaded = path.read_text(encoding="utf-8").strip()
            if loaded:
                os.environ[_ENV_KEY] = loaded
                return loaded
    except OSError as exc:
        logger.warning("could not read API token secret file %s: %s", path, exc)

    minted = secrets.token_urlsafe(48)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(minted + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        os.environ[_ENV_KEY] = minted
        logger.warning(
            "minted %s and wrote %s — copy into .env for backup across rebuilds",
            _ENV_KEY,
            path,
        )
        return minted
    except OSError as exc:
        if _is_production_config():
            raise RuntimeError(
                f"{_ENV_KEY} must be set (or writable at {path}) when "
                "FLASK_CONFIG=production; refusing in-memory-only JWT secret"
            ) from exc
        os.environ[_ENV_KEY] = minted
        logger.warning(
            "minted %s in-process but could not persist to %s: %s",
            _ENV_KEY,
            path,
            exc,
        )
        return minted
