"""Phase 7: queue row-locking default-on for Postgres (refuse silent degrade)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from application.utils.rag_parity.flags import RagParityFlags, load_flags


class QueueLockError(RuntimeError):
    """Raised when locking was required but the dialect cannot provide it."""


@dataclass(frozen=True)
class LockPolicy:
    lock_rows: bool
    dialect: str
    reason: str


def resolve_queue_lock_policy(
    *,
    dialect: str,
    dry_run: bool = False,
    flags: Optional[RagParityFlags] = None,
) -> LockPolicy:
    """Postgres consumers must SKIP LOCKED when flag default-on and not dry-run.

    SQLite / unknown dialects refuse rather than silently dropping the lock when
    ``queue_row_lock_default`` is True (parity with Librarian knowledge_source).
    """
    cfg = flags or load_flags()
    d = (dialect or "").lower()
    if dry_run:
        return LockPolicy(lock_rows=False, dialect=d, reason="dry_run")
    if d == "postgresql":
        return LockPolicy(
            lock_rows=bool(cfg.queue_row_lock_default),
            dialect=d,
            reason="postgres_skip_locked",
        )
    if not cfg.queue_row_lock_default:
        return LockPolicy(lock_rows=False, dialect=d, reason="flag_off")
    if d in ("sqlite", ""):
        # Hermetic unit fakes may pass empty dialect with no concurrency.
        if d == "":
            return LockPolicy(lock_rows=False, dialect=d, reason="no_bind_fake")
        raise QueueLockError(
            "CRE_RAG_PARITY_QUEUE_ROW_LOCK requires PostgreSQL SKIP LOCKED; "
            f"refusing silent degrade on dialect={d!r}"
        )
    raise QueueLockError(
        f"unsupported dialect {d!r} for queue row locking; refuse silent degrade"
    )


def apply_skip_locked(query: Any, policy: LockPolicy) -> Any:
    if not policy.lock_rows:
        return query
    return query.with_for_update(skip_locked=True)
