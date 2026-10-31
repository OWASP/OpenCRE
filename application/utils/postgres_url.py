"""Normalize Postgres URLs for SQLAlchemy and the installed psycopg2 driver.

SQLAlchemy 2.1 maps a bare ``postgresql://`` URL to the psycopg v3 dialect.
This repo installs ``psycopg2-binary``, so engines must use
``postgresql+psycopg2://``.
"""

from __future__ import annotations


def is_postgres_url(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered.startswith(
        (
            "postgresql://",
            "postgres://",
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
    )


def sqlalchemy_postgres_url(value: str) -> str:
    """Return a SQLAlchemy URL that uses the psycopg2 dialect."""
    raw = (value or "").strip()
    if not is_postgres_url(raw):
        raise ValueError(f"not a Postgres URL: {raw!r}")
    return "postgresql+psycopg2://" + raw.split("://", 1)[1]
