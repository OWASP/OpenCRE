"""Normalize Postgres URLs for SQLAlchemy + the project's psycopg2 driver.

SQLAlchemy 2.1 maps bare ``postgresql://`` to the psycopg v3 dialect. This
repo installs ``psycopg2-binary`` (see ``requirements.txt``), so engines must
use ``postgresql+psycopg2://``.
"""

from __future__ import annotations

# Matches ``make docker-postgres`` (user cre / password / db cre).
DEFAULT_LOCAL_POSTGRES_URL = "postgresql://cre:password@127.0.0.1:5432/cre"


def is_postgres_url(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return (
        lowered.startswith("postgresql://")
        or lowered.startswith("postgres://")
        or lowered.startswith("postgresql+psycopg2://")
        or lowered.startswith("postgresql+psycopg://")
    )


def sqlalchemy_postgres_url(value: str) -> str:
    """Return a SQLAlchemy URL that uses the psycopg2 dialect.

    Raises ``ValueError`` for empty or non-Postgres URLs (including sqlite).
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Postgres URL is empty")
    lowered = raw.lower()
    if lowered.startswith("sqlite:"):
        raise ValueError("Postgres required; sqlite URLs are not allowed")
    if not is_postgres_url(raw):
        raise ValueError(f"not a Postgres URL: {raw!r}")
    # Always pin psycopg2 — bare postgresql:// and +psycopg map to v3 in SA 2.1.
    if "://" not in raw:
        raise ValueError(f"not a Postgres URL: {raw!r}")
    return "postgresql+psycopg2://" + raw.split("://", 1)[1]


def main_db_env_keys(flask_config: str = "development") -> tuple[str, ...]:
    """Env keys Flask / admin / agent consult for the main DB (same order)."""
    cfg = (flask_config or "development").strip().lower()
    if cfg in ("production", "prod"):
        # Heroku sets DATABASE_URL; PROD_DATABASE_URL is an optional local alias.
        return ("DATABASE_URL", "PROD_DATABASE_URL", "SQLALCHEMY_DATABASE_URI")
    return ("DEV_DATABASE_URL", "DATABASE_URL", "SQLALCHEMY_DATABASE_URI")
