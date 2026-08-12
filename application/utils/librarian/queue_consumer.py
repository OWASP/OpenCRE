"""Module C's write-back to Module B's queue: stamp ``consumed_at``.

The mirror image of Module B's ``queue_writer``. B inserts rows and C retires
them — ``db.KnowledgeQueueItem``'s own docstring assigns this side to C:
*"Module C reads unconsumed rows and sets consumed_at."*

This is the only place Module C writes to Module B's table, and it writes
exactly one column. It never deletes a row: the queue doubles as the audit trail
of what B handed over and what C did with it.

Idempotent by construction — the update is filtered on ``consumed_at IS NULL``,
so replaying a run cannot move a timestamp that is already set. The count
returned is rows actually stamped, which is why it can be lower than the number
of ids passed in (a concurrent run got there first, or the id no longer exists).

The caller owns the transaction, matching ``run_noise_filter`` on B's side.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence

logger = logging.getLogger(__name__)

# Postgres has a bind-parameter ceiling and a huge IN (...) plans badly, so the
# id list is stamped in chunks rather than one statement.
_CHUNK_SIZE = 500


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def mark_consumed(session: Any, row_ids: Iterable[str], *, at: datetime) -> int:
    """Stamp ``consumed_at = at`` on the given rows; return how many were stamped.

    ``at`` is injected rather than read from the clock so a run is reproducible
    and so every row in one batch carries the same timestamp — that shared value
    is what makes a run's consumption identifiable after the fact.
    """
    unique: List[str] = list(dict.fromkeys(rid for rid in row_ids if rid))
    if not unique:
        return 0

    from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow

    # `consumed_at` is a plain `DateTime`, and the B->C contract is explicit that
    # the UTC wall clock is "stored and read back timezone-naive". Handing an
    # aware datetime to a naive column is dialect-dependent: SQLite keeps the
    # offset in the string, Postgres drops it. Converting to UTC first and then
    # stripping tzinfo makes the stored instant correct under both, and matches
    # the `created_at` values B writes alongside it.
    stamp = at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at

    stamped = 0
    for chunk in _chunks(unique, _CHUNK_SIZE):
        stamped += (
            session.query(KnowledgeQueueRow)
            .filter(
                KnowledgeQueueRow.id.in_(list(chunk)),
                KnowledgeQueueRow.consumed_at.is_(None),
            )
            .update({KnowledgeQueueRow.consumed_at: stamp}, synchronize_session=False)
        )

    if stamped != len(unique):
        # Not an error: another worker may have taken the row, or B may have
        # pruned it. Worth a line, because a persistent gap means C is
        # re-reading rows it believes it finished.
        logger.info(
            "librarian queue write-back: stamped %d of %d rows consumed "
            "(the rest were already consumed or no longer exist)",
            stamped,
            len(unique),
        )
    return stamped


__all__ = ["mark_consumed"]
