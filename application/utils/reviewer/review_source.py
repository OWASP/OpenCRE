"""Where Module D reads pending reviews from.

``DbReviewSource`` is D's counterpart to Module C's ``DbKnowledgeSource``: the
read side of a queue handoff, deliberately the same shape so anyone who has read
one can read the other. It selects ``status='review_required' AND consumed_at IS
NULL`` from ``decision_queue`` — never ``linked`` rows, which belong to the
graph writer — validates each row's ``envelope`` column back into the RFC
``ReviewItem`` it was written from, and yields both together.

The envelope is validated through the *same* pinned model Module C emitted it
with (``application.utils.librarian.schemas.ReviewItem``), so C and D cannot
drift apart on what a review item is without one of them failing loudly.

**One consumer at a time.** The read is not atomic with the ``consumed_at``
stamp, exactly as on the B->C queue, and for the same reason the same rule
applies: run a single reviewer service per queue. The row-locking lesson from
#1025 is documented there; D inherits the single-consumer contract rather than
paying for locks it does not need yet.

**Rows D cannot model are skipped, reported, and left unconsumed.** This is the
opposite of C's poison-row policy, on purpose. A ``knowledge_queue`` row C could
not model was B's input, safe to retire because C's refusal was the decision. A
``decision_queue`` row D cannot parse is *C's output and the audit record of a
decision*: retiring it would hide a C-side contract breach from the one queue
where a human would eventually see it. The ids surface in
``unreadable_row_ids`` so a run can alert on them instead.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Iterator, List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from application.utils.librarian.schemas import ReviewItem

#: The only status this package may touch, in reads and write-backs alike.
REVIEWABLE_STATUS = "review_required"
#: Rows loaded per query while walking the queue.
_BATCH_SIZE = 100


class PendingReview(BaseModel):
    """One decision_queue row awaiting a human, envelope already validated.

    The scalar columns are projections C made for filtering; the envelope is the
    document of record. Both are carried so the review UI can list cheaply and
    drill into the full audit without a second query.
    """

    model_config = ConfigDict(extra="forbid")

    row_id: str
    chunk_id: str
    artifact_id: str
    pipeline_run_id: str
    source_label: Optional[str]
    reason_code: Optional[str]
    confidence: Optional[float]
    created_at: datetime
    envelope: ReviewItem


class ReviewSource(ABC):
    @abstractmethod
    def items(self) -> Iterator[PendingReview]:
        """Yield decision_queue rows awaiting human review."""
        raise NotImplementedError


class DbReviewSource(ReviewSource):
    """Reads unconsumed ``review_required`` rows from ``decision_queue``.

    The caller owns the session, as everywhere else in this pipeline: this class
    never opens, commits, or closes a transaction. Retiring a row is a separate,
    explicit step (``queue_consumer.mark_reviewed``) that only happens after the
    verdict is durably recorded.

    ``pipeline_run_id`` scopes to one orchestrator pass; left unset, the source
    drains every pending review, which is what a standing review inbox wants.
    ``limit`` caps the readable items in one page, so unreadable rows, which stay
    unconsumed and sort first forever, cannot starve it. Rows are ordered by
    ``created_at`` then ``id`` so a limited page is stable and reproducible.
    """

    def __init__(
        self,
        session: object,
        *,
        pipeline_run_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        self._session = session
        self._run_id = pipeline_run_id
        self._limit = limit
        #: Rows whose envelope failed validation. Never consumed by D — see the
        #: module docstring for why this deliberately differs from C.
        self.unreadable_row_ids: List[str] = []

    def _rows(self) -> Iterator[Any]:
        """Walk the matching rows in order, in batches.

        The ordered ids are read first and rows loaded by id. OFFSET would shift
        if a caller stamps rows between batches, and comparing ``created_at``
        fails on SQLite, where the stored text and the bound value differ. The
        filters are re-applied per batch, so a row stamped meanwhile is skipped.
        """
        # Lazy import, same reason as the librarian: this package stays DB-free
        # at import time so its tests and models are hermetic.
        from application.database.db import DecisionQueueItem

        query = self._session.query(DecisionQueueItem).filter(  # type: ignore[attr-defined]
            DecisionQueueItem.consumed_at.is_(None),
            DecisionQueueItem.status == REVIEWABLE_STATUS,
        )
        if self._run_id:
            query = query.filter(DecisionQueueItem.pipeline_run_id == self._run_id)
        query = query.order_by(DecisionQueueItem.created_at, DecisionQueueItem.id)

        ids = [row_id for (row_id,) in query.with_entities(DecisionQueueItem.id)]
        for start in range(0, len(ids), _BATCH_SIZE):
            batch = ids[start : start + _BATCH_SIZE]
            yield from query.filter(DecisionQueueItem.id.in_(batch)).all()

    def items(self) -> Iterator[PendingReview]:
        self.unreadable_row_ids = []
        if self._limit is not None and self._limit <= 0:
            return
        yielded = 0
        for row in self._rows():
            try:
                item = PendingReview(
                    row_id=row.id,
                    chunk_id=row.chunk_id,
                    artifact_id=row.artifact_id,
                    pipeline_run_id=row.pipeline_run_id,
                    source_label=row.source_label,
                    reason_code=row.reason_code,
                    confidence=row.confidence,
                    created_at=row.created_at,
                    envelope=ReviewItem.model_validate(row.envelope),
                )
            except ValidationError as exc:
                # A C-side contract breach worth seeing, but one bad row must
                # not take the review inbox down. Ids are safe to log; the
                # envelope's text is not.
                row_id = getattr(row, "id", None)
                logger.warning(
                    "Skipping unreadable decision_queue row id=%s: %s",
                    row_id if row_id is not None else "<unknown>",
                    exc.errors(include_input=False),
                )
                if row_id is not None:
                    self.unreadable_row_ids.append(row_id)
                continue
            yield item
            yielded += 1
            if self._limit is not None and yielded >= self._limit:
                return
