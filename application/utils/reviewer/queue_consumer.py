"""Module D's write-back to ``decision_queue``: stamp ``consumed_at``.

The mirror of Module C's ``queue_consumer`` against Module B's queue, and it
follows the same three rules: exactly one column is written, nothing is ever
deleted (the queue doubles as the audit trail), and the update is filtered on
``consumed_at IS NULL`` so a replay cannot move a timestamp that is already set.

One rule is D's own: **the filter also requires ``status='review_required'``.**
``linked`` rows belong to the graph writer, and a human-review service must be
structurally unable to retire one, even by bug or by being handed the wrong id.
Passing a linked row's id here is therefore a silent no-op, counted in the gap
between ids passed and rows stamped, exactly like an id that no longer exists.

Call order is fixed by the package rule: record the verdict in the corrections
log first, stamp here second. A crash between the two leaves the row unconsumed
and the verdict re-recordable — never the other way round, where the row is
retired and the verdict lost.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence

from application.utils.reviewer.review_source import REVIEWABLE_STATUS

# Same bind-parameter ceiling reasoning as Module C's write-back.
_CHUNK_SIZE = 500


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def mark_reviewed(session: Any, row_ids: Iterable[str], *, at: datetime) -> int:
    """Stamp ``consumed_at = at`` on the given review rows; return rows stamped.

    ``at`` is injected rather than read from the clock so a run is reproducible
    and every row retired by one review session carries the same timestamp.
    """
    unique: List[str] = list(dict.fromkeys(rid for rid in row_ids if rid))
    if not unique:
        return 0

    from application.database.db import DecisionQueueItem

    # `consumed_at` is a plain DateTime, stored naive-UTC across both dialects,
    # same as everywhere else in the pipeline. Convert-then-strip keeps the
    # stored instant correct under SQLite and Postgres alike.
    stamp = at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at

    stamped = 0
    for chunk in _chunks(unique, _CHUNK_SIZE):
        stamped += (
            session.query(DecisionQueueItem)
            .filter(
                DecisionQueueItem.id.in_(list(chunk)),
                DecisionQueueItem.consumed_at.is_(None),
                DecisionQueueItem.status == REVIEWABLE_STATUS,
            )
            .update({DecisionQueueItem.consumed_at: stamp}, synchronize_session=False)
        )

    if stamped != len(unique):
        # Not an error: an id may be already consumed, gone, or — the case this
        # module exists to make impossible to act on — a linked row.
        logger.info(
            "reviewer write-back: stamped %d of %d rows consumed "
            "(the rest were already consumed, linked, or no longer exist)",
            stamped,
            len(unique),
        )
    return stamped


__all__ = ["mark_reviewed"]
