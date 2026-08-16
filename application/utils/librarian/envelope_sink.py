"""Where C's envelopes go once they are built.

Retiring a queue row is only safe if the envelope built from it survived
somewhere. A run that stamps ``consumed_at`` and drops the ``LinkProposal`` on
the floor has destroyed that chunk: B will not re-offer the row, and nothing
downstream ever saw the decision. So consumption is defined against a sink, not
against the pipeline having finished.

Two implementations here:

- ``JsonlEnvelopeSink`` — appends one JSON envelope per line. Durable, greppable,
  and enough to make a live drain lossless before the graph writer exists.
- ``NullEnvelopeSink`` — counts and discards, for dry runs. It reports
  ``persists=False``, and the runner refuses to consume behind it.

The graph / review-queue writers (W8b) become further implementations of the
same protocol, so the consumption rule does not have to change when they land.
"""

import json
import logging
import os
from typing import Any, List, Mapping, Optional, Protocol, Sequence, Union

from application.utils.librarian.schemas import LinkProposal, ReviewItem

logger = logging.getLogger(__name__)

Envelope = Union[LinkProposal, ReviewItem]


class EnvelopeSink(Protocol):
    """Somewhere an envelope can be durably put."""

    @property
    def persists(self) -> bool:
        """True when a written envelope outlives the process.

        The runner reads this to decide whether retiring the source row would
        lose work; a sink that answers False can never trigger consumption.
        """
        ...

    def write(self, envelopes: Sequence[Envelope]) -> int:
        """Persist the batch; return how many were written."""
        ...


class NullEnvelopeSink:
    """Accepts envelopes and keeps nothing. For dry runs and tests."""

    def __init__(self) -> None:
        self.written = 0

    @property
    def persists(self) -> bool:
        return False

    def write(self, envelopes: Sequence[Envelope]) -> int:
        self.written += len(envelopes)
        return len(envelopes)


class JsonlEnvelopeSink:
    """Appends envelopes to a JSONL file, one RFC envelope per line.

    **This is a mirror, not the handoff.** ``decision_queue`` is where a decision
    is recorded and where Module D reads it; ``DbEnvelopeSink`` owns that, and it
    is idempotent per ``(chunk_id, pipeline_run_id)``. This sink exists so a run
    can be eyeballed or grepped, and it deliberately offers weaker guarantees:

    - **No cross-process coordination.** Two runs appending to the same path can
      interleave. Give concurrent runs separate files.
    - **No dedup.** A replayed run appends its envelopes again, so a chunk can
      appear more than once. The chunk id and run id on each record are what let
      a reader collapse duplicates.

    Neither weakens the consumption rule, because a real run always writes
    ``decision_queue`` too: rows are retired on the strength of that insert, not
    of this file.

    Append rather than truncate: several runs over different
    ``pipeline_run_id``s share one output file, and each envelope already
    carries its own run id. ``model_dump_json`` is used so the file holds the
    same RFC shape Module D will consume, datetimes and enums included.

    ``exclude_none=True`` is not cosmetic. The vendored RFC schemas type their
    optional fields as plain ``"string"`` and leave them out of ``required``,
    so an absent value must be an *absent key* — emitting ``"repo": null``
    fails validation against the very schema this file is supposed to satisfy.
    Every rss envelope trips it (no ``repo``/``commit_sha``), and so does every
    github one (no ``feed_url``/``post_guid``). Writing the null would hand
    Module D a file its own validator rejects.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes: Sequence[Envelope]) -> int:
        if not envelopes:
            return 0
        parent = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(parent, exist_ok=True)
        lines: List[str] = [e.model_dump_json(exclude_none=True) for e in envelopes]
        # One open/flush for the batch, and the newline goes after every record
        # so a partially written run still parses line by line.
        with open(self._path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        logger.info("wrote %d envelopes to %s", len(lines), self._path)
        return len(lines)


class DbEnvelopeSink:
    """Writes envelopes to ``decision_queue`` — the C -> D handoff.

    The mirror image of Module B's ``queue_writer``: B inserts the rows C reads,
    and this inserts the rows Module D reads. Same shape of handoff, same
    properties — one row per decided chunk, both outcomes in one table separated
    by ``status``, nothing ever deleted, and the reader retires a row by setting
    ``consumed_at``.

    **Idempotent by construction.** The insert is
    ``ON CONFLICT (chunk_id, pipeline_run_id) DO NOTHING``, so replaying a run
    that already wrote its decisions is a no-op rather than a duplicate or an
    aborted batch — the same DB-level idempotence B relies on for
    ``content_hash``. The count returned is rows actually inserted, which is why
    it can be lower than the batch size.

    Since a row that was already there *is* persisted, a replay still satisfies
    the consumption rule: the runner may retire the queue rows behind it.

    The DB import is function-local, keeping the rest of the package importable
    without SQLAlchemy — the same rule ``knowledge_source`` and ``queue_consumer``
    follow on the read side.
    """

    def __init__(
        self,
        session: Any,
        pipeline_run_id: str,
        source_labels: Optional[dict] = None,
    ) -> None:
        self._session = session
        self._run_id = pipeline_run_id
        # chunk_id -> B's llm_label. The RFC envelope is pinned and has no field
        # for it, so it travels beside the envelopes and is recorded on the row.
        self._source_labels = dict(source_labels or {})

    def accept_source_labels(self, labels: Mapping[str, str]) -> None:
        """Take the chunk_id -> B-label map the run produced.

        Optional on the sink protocol: a sink that has nowhere to put the label
        simply does not implement it, and the runner skips the call. Declared as
        a method rather than letting the caller reach into the attribute, so the
        seam is visible to anyone writing a new sink.
        """
        self._source_labels.update(labels)

    @property
    def persists(self) -> bool:
        return True

    def write(self, envelopes: Sequence[Envelope]) -> int:
        if not envelopes:
            return 0

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from application.database.db import DecisionQueueItem, generate_uuid

        mismatched = sorted(
            {e.pipeline_run_id for e in envelopes if e.pipeline_run_id != self._run_id}
        )
        if mismatched:
            # The row is keyed on the envelope's run id while the runner is
            # consuming rows for this sink's run id. Letting that through writes
            # the decision under one run and retires the source row under
            # another, so the (chunk, run) uniqueness stops protecting anything
            # and the provenance no longer joins up.
            raise ValueError(
                f"DbEnvelopeSink was built for pipeline_run_id={self._run_id!r} "
                f"but was handed envelopes from {mismatched!r}; a decision must "
                "be written under the run that produced it."
            )

        rows = [self._row(e) for e in envelopes]
        dialect = self._session.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(DecisionQueueItem.__table__).values(rows)
        statement = statement.on_conflict_do_nothing(
            index_elements=["chunk_id", "pipeline_run_id"]
        )
        result = self._session.execute(statement)

        # rowcount is the authority on what was actually inserted; a replay
        # legitimately reports fewer rows than it was handed.
        written = result.rowcount if result.rowcount is not None else len(rows)
        if written != len(rows):
            logger.info(
                "decision_queue: inserted %d of %d envelopes for run %s "
                "(the rest were already written by an earlier run)",
                written,
                len(rows),
                self._run_id,
            )
        else:
            logger.info("decision_queue: inserted %d envelopes", written)
        return written

    def _row(self, envelope: Envelope) -> dict:
        """Project one envelope into a ``decision_queue`` row.

        The envelope itself is stored whole; these columns exist so Module D can
        filter without parsing JSON, and are read back off the same document.
        """
        from application.database.db import generate_uuid

        is_review = envelope.status == "review_required"
        return {
            "id": generate_uuid(),
            "chunk_id": envelope.chunk_id,
            "artifact_id": envelope.artifact_id,
            "pipeline_run_id": envelope.pipeline_run_id,
            "schema_version": envelope.schema_version,
            "source_label": self._source_labels.get(envelope.chunk_id),
            "status": envelope.status,
            "reason_code": (
                envelope.reason_code.value
                if is_review and envelope.reason_code is not None
                else None
            ),
            "review_id": envelope.review_id if is_review else None,
            "confidence": _top_confidence(envelope),
            "envelope": json.loads(envelope.model_dump_json(exclude_none=True)),
        }


class TeeEnvelopeSink:
    """Writes the same batch to several sinks, reporting the first one's count.

    Used to mirror a live run to JSONL while `decision_queue` stays the actual
    contract: the first sink is the one whose count is authoritative, the rest
    are copies. Ordered on purpose — the contract sink is written first, so a
    failure in a mirror cannot leave the handoff half-done.

    ``persists`` is True only if *every* sink persists. A tee that included a
    discarding sink would otherwise let a run consume rows on the strength of a
    copy that kept nothing.
    """

    def __init__(self, *sinks: "EnvelopeSink") -> None:
        if not sinks:
            raise ValueError("TeeEnvelopeSink needs at least one sink")
        self._sinks = sinks

    @property
    def persists(self) -> bool:
        return all(s.persists for s in self._sinks)

    def write(self, envelopes: Sequence[Envelope]) -> int:
        written = self._sinks[0].write(envelopes)
        for mirror in self._sinks[1:]:
            mirror.write(envelopes)
        return written


def _top_confidence(envelope: Envelope) -> Optional[float]:
    """The calibrated confidence behind the decision, when there is one.

    A linked envelope always carries its link; a review envelope may carry
    suggested links, or none at all when nothing was retrieved.
    """
    links = getattr(envelope, "links", None) or getattr(
        envelope, "suggested_links", None
    )
    if not links:
        return None
    # Max, not first: nothing in the schema orders `links`, so taking [0] could
    # project a lower number than the envelope Module D filters on actually
    # carries — and the column is meant to be readable off that same document.
    return max(link.confidence for link in links)


def envelope_id(envelope: Envelope) -> str:
    """The chunk an envelope speaks for — handy for logs and tests."""
    return envelope.chunk_id


__all__ = [
    "DbEnvelopeSink",
    "TeeEnvelopeSink",
    "EnvelopeSink",
    "JsonlEnvelopeSink",
    "NullEnvelopeSink",
    "envelope_id",
]
