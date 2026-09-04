"""Where Module C reads accepted chunks from.

Defines the source interface plus two implementations:

- ``FixtureKnowledgeSource`` — a JSONL file, for tests and offline dry-runs.
- ``DbKnowledgeSource`` — the live reader over Module B's ``knowledge_queue``
  table (merged in #989), which is what the orchestrator runs against.

Both yield the same ``KnowledgeQueueItem`` mirror, so the pipeline cannot tell
them apart; C synthesizes the RFC envelope from each row downstream.

**Both of B's labels are read.** B drops ``NOISE`` and writes ``KNOWLEDGE`` and
``UNCERTAIN``; recall-first is the point, so an ``UNCERTAIN`` chunk is one B was
not confident *classifying*, not one it judged worthless. C originally read only
``KNOWLEDGE`` and left the rest for Module D, which stranded them: nothing
retrieved candidates for them, so a human would have had to review raw text with
no CRE suggestions, and until D exists they simply accumulated.

C now reads both. What differs is the weight the label carries downstream, not
whether the chunk is looked at — every decision row records the label it came
from, so a consumer can tell a decision made on a confident chunk from one made
on an uncertain one.
"""

import logging
from abc import ABC, abstractmethod
from typing import Iterator, List, Optional

from pydantic import ValidationError

from application.utils.librarian.schemas import KnowledgeQueueItem

logger = logging.getLogger(__name__)

# The labels Module C acts on; see the module docstring. NOISE never reaches the
# queue — B drops it — so these two are everything B writes.
KNOWLEDGE_LABEL = "KNOWLEDGE"
UNCERTAIN_LABEL = "UNCERTAIN"
READABLE_LABELS = (KNOWLEDGE_LABEL, UNCERTAIN_LABEL)


class KnowledgeSource(ABC):
    @abstractmethod
    def items(self) -> Iterator[KnowledgeQueueItem]:
        """Yield knowledge_queue rows awaiting classification."""
        raise NotImplementedError


class FixtureKnowledgeSource(KnowledgeSource):
    """Reads knowledge_queue rows from a JSONL fixture (one JSON object per line)."""

    def __init__(self, jsonl_path: str) -> None:
        self._path = jsonl_path

    def items(self) -> Iterator[KnowledgeQueueItem]:
        with open(self._path, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if line:
                    try:
                        yield KnowledgeQueueItem.model_validate_json(line)
                    except ValidationError as exc:
                        # Log only error locations/types, never the raw input —
                        # queue rows can carry sensitive content.
                        logger.warning(
                            "Skipping malformed knowledge_queue row at line %d: %s",
                            line_no,
                            exc.errors(include_input=False),
                        )
                        continue


class DbKnowledgeSource(KnowledgeSource):
    """Reads unconsumed ``KNOWLEDGE`` and ``UNCERTAIN`` rows from B's live queue.

    The caller owns the session (mirroring Module B's ``run_noise_filter``), so
    this class never opens, commits, or closes a transaction — it only reads.
    Marking a row consumed is a separate, explicit step; see ``queue_consumer``.

    ``pipeline_run_id`` scopes a run to one orchestrator pass. Left unset, C
    drains every unconsumed row regardless of which run produced it, which is
    what a standalone catch-up run wants. ``limit`` caps one batch.

    Rows are ordered by ``created_at`` then ``id``: the timestamp alone is not
    unique (B inserts a batch inside one transaction), and an unstable order
    would make a ``limit``ed run non-reproducible.

    **One consumer at a time, unless ``lock_rows`` is set.** The read selects on
    ``consumed_at IS NULL``, and ``consumed_at`` is only stamped once the batch
    has been mapped and persisted. The claim is therefore not atomic with the
    read: for the whole length of a run, a second consumer selecting the same
    predicate sees the same rows. With ``limit`` set it sees *exactly* the same
    rows, because the order is deterministic and nothing marks a row as taken —
    so two plain consumers duplicate each other's work entirely rather than
    splitting it. The orchestrator runs one C consumer per ``pipeline_run_id``,
    which is what makes the default safe; see #1025.

    Duplicated work is the cost, not corruption: ``decision_queue`` is unique on
    ``(chunk_id, pipeline_run_id)`` and the ``consumed_at`` update is filtered on
    ``IS NULL``, so a doubled batch converges on the same rows. What it wastes is
    the embedding and cross-encoder passes, which are the expensive part.

    ``lock_rows=True`` is what makes concurrent consumers actually disjoint. It
    is opt-in because the lock has to be held for the length of the run to mean
    anything (see ``_locked``), and because a single consumer gains nothing from
    paying for it.
    """

    def __init__(
        self,
        session: object,
        *,
        pipeline_run_id: Optional[str] = None,
        limit: Optional[int] = None,
        lock_rows: bool = False,
    ) -> None:
        self._session = session
        self._run_id = pipeline_run_id
        self._limit = limit
        self._lock_rows = lock_rows
        #: Ids of rows B wrote that C could not model, filled during iteration.
        #: They never reach the pipeline, so the pipeline cannot report them as
        #: finished — without this the runner would leave them unconsumed and
        #: re-read the same poison rows on every run, forever. The runner adds
        #: them to the consumed set: a row that fails the model is a definitive
        #: refusal, exactly like a C.0 boundary rejection, and the row itself
        #: stays in the table as the record of what happened.
        self.rejected_row_ids: List[str] = []

    def _query(self) -> object:
        # Imported lazily: the schemas/pipeline layers stay DB-free by design,
        # and this keeps `import knowledge_source` cheap for hermetic tests.
        from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow

        query = self._session.query(KnowledgeQueueRow).filter(  # type: ignore[attr-defined]
            KnowledgeQueueRow.consumed_at.is_(None),
            KnowledgeQueueRow.llm_label.in_(READABLE_LABELS),
        )
        if self._run_id:
            query = query.filter(KnowledgeQueueRow.pipeline_run_id == self._run_id)
        query = query.order_by(KnowledgeQueueRow.created_at, KnowledgeQueueRow.id)
        if self._limit is not None:
            query = query.limit(self._limit)
        if self._lock_rows:
            query = self._locked(query)
        return query

    def _locked(self, query: object) -> object:
        """Add ``FOR UPDATE SKIP LOCKED`` so concurrent consumers claim disjoint rows.

        The lock is only meaningful because of where the transaction ends. This
        class never commits; the caller does, and ``run_librarian_queue`` commits
        *after* the write-back. So the rows a consumer locks here stay locked
        through mapping, persistence, and the ``consumed_at`` stamp — one
        transaction covering the whole claim, which is the property that makes a
        second consumer's ``SKIP LOCKED`` skip the right rows.

        That is also the cost: the lock is held across C.1's embedding calls and
        C.2's cross-encoder passes, so a batch's rows stay locked for as long as
        the batch takes to decide. Module B inserts into this same table, so a
        long-running locked batch is contention B pays for. Keep ``limit`` small
        enough that a batch is minutes, not hours. The lock-free alternative is a
        dedicated claim column on ``knowledge_queue``, which is B's schema to
        change, not C's.

        Note that ``LIMIT`` and ``SKIP LOCKED`` interact: Postgres applies the
        limit to the scan and *then* drops rows another consumer holds, so a
        locked batch can come back smaller than ``limit`` — sometimes empty —
        while unclaimed rows remain. Callers must treat a short batch as "keep
        draining", not as "the queue is empty".
        """
        from application.database.pgvector_utils import connection_dialect_name

        dialect = connection_dialect_name(self._session)
        if dialect == "postgresql":
            return query.with_for_update(skip_locked=True)  # type: ignore[attr-defined]
        if not dialect:
            # Hermetic test fakes carry no bind and no concurrency to guard.
            return query
        # Refuse rather than degrade. SQLite has no FOR UPDATE SKIP LOCKED, and
        # silently dropping the clause would hand back an unlocked batch to a
        # caller who asked for a locked one — the failure would surface as
        # duplicated work under load, far from here.
        raise ValueError(
            f"lock_rows=True needs Postgres for FOR UPDATE SKIP LOCKED; this "
            f"session is {dialect!r}. Run a single consumer instead (the "
            f"default), which is safe without row locks."
        )

    def items(self) -> Iterator[KnowledgeQueueItem]:
        for row in self._query():  # type: ignore[attr-defined]
            try:
                yield KnowledgeQueueItem.model_validate(row)
            except ValidationError as exc:
                # A row B wrote that C cannot model is a contract breach worth
                # seeing, but it must not abort the batch. Ids are safe to log;
                # the row's text is not.
                row_id = getattr(row, "id", None)
                logger.warning(
                    "Skipping unmodellable knowledge_queue row id=%s: %s",
                    row_id if row_id is not None else "<unknown>",
                    exc.errors(include_input=False),
                )
                if row_id is not None:
                    self.rejected_row_ids.append(row_id)
                continue
