"""Database backend capability helpers for import/runtime instrumentation."""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import dataclass

from application.utils.postgres_url import is_postgres_url


@dataclass(frozen=True)
class BackendCapabilities:
    backend: str
    is_postgres: bool
    supports_pair_ga_scheduler: bool
    reason: str


def detect_backend(db_connection_str: str) -> BackendCapabilities:
    """Best-effort backend detection from SQLAlchemy connection string."""
    conn = (db_connection_str or "").strip()
    if is_postgres_url(conn):
        return BackendCapabilities(
            backend="postgres",
            is_postgres=True,
            supports_pair_ga_scheduler=True,
            reason="postgres backend detected",
        )
    lowered = conn.lower()
    if lowered.startswith("sqlite://") or lowered.endswith(".sqlite") or conn == "":
        return BackendCapabilities(
            backend="sqlite",
            is_postgres=False,
            supports_pair_ga_scheduler=False,
            reason="sqlite backend detected",
        )
    return BackendCapabilities(
        backend="unknown",
        is_postgres=False,
        supports_pair_ga_scheduler=False,
        reason="unknown backend (treat as not pair-ga-capable)",
    )
