"""Per-job mutual exclusion so overlapping ticks never run one job twice.

On Postgres the lease is a session-level advisory lock held on a dedicated
connection for the whole run, so it is released by the server if the process
dies. Other dialects (the in-memory test database) fall back to a process-local
lock, which is enough to exercise the contract but is not a cross-process guard.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import hashlib
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator

import sqlalchemy as sa

_LOCAL_LOCKS: Dict[str, threading.Lock] = {}
_LOCAL_GUARD = threading.Lock()


def lease_key(job: str) -> int:
    """Stable signed 63-bit advisory-lock key for ``job``."""
    digest = hashlib.sha256(f"opencre:oie:{job}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


@contextmanager
def job_lease(session: Any, job: str) -> Iterator[bool]:
    """Yield True when this caller holds the lease for ``job``, else False."""
    engine = session.get_bind()
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            acquired = bool(
                conn.execute(
                    sa.text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": lease_key(job)},
                ).scalar()
            )
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute(
                        sa.text("SELECT pg_advisory_unlock(:key)"),
                        {"key": lease_key(job)},
                    )
        return

    with _LOCAL_GUARD:
        lock = _LOCAL_LOCKS.setdefault(job, threading.Lock())
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
