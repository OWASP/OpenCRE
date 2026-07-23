"""Module B output stage: write classified chunks to `knowledge_queue`.

This is Module B's DB boundary. It maps a (ChangeRecord, ClassifyResult,
content_hash) triple into a `knowledge_queue` row and inserts the keepers with
DB-level idempotence (`INSERT ... ON CONFLICT (content_hash) DO NOTHING`), so a
concurrent or replayed run that produces the same content never aborts the
batch. NOISE verdicts are dropped (they never reach the queue); KNOWLEDGE and
UNCERTAIN are written (UNCERTAIN is for Module D's HITL review). Module C reads
from `knowledge_queue`; see module_c_contract.md (v0.2).

The classifier and schemas stay DB-free by design; this module is the only
part of Module B that imports the SQLAlchemy layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from application.database.db import KnowledgeQueueItem, generate_uuid
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult


@dataclass(frozen=True)
class WriteStats:
    """Outcome of writing a batch of verdicts to the queue."""

    inserted: int = 0
    deduped: int = 0
    dropped_noise: int = 0


def _row_values(
    record: ChangeRecord, verdict: ClassifyResult, content_hash: str
) -> dict:
    """Map one classified record to a `knowledge_queue` column dict.

    All provenance columns are present (None where not applicable) so a batch
    insert has uniform keys. `created_at` is left to the server default.
    """
    source = record.source
    is_github = source.type == "github"
    is_rss = source.type == "rss"
    return {
        "id": generate_uuid(),
        "content_hash": content_hash,
        "chunk_id": record.chunk_id,
        "artifact_id": record.artifact_id,
        "pipeline_run_id": record.pipeline_run_id,
        "schema_version": record.schema_version,
        "source_type": source.type,
        "source_repo": source.repo if is_github else None,
        "source_commit_sha": source.commit_sha if is_github else None,
        "source_committed_at": source.committed_at if is_github else None,
        "feed_url": source.feed_url if is_rss else None,
        "post_guid": source.post_guid if is_rss else None,
        "locator_kind": record.locator.kind,
        "locator_path": record.locator.path,
        "span_index": record.span.index,
        "span_total": record.span.total,
        "span_heading_path": json.dumps(record.span.heading_path),
        "text": record.text,
        "llm_label": verdict.label,
        "confidence": verdict.confidence,
        "llm_reasoning": verdict.reasoning,
    }


def to_queue_item(
    record: ChangeRecord, verdict: ClassifyResult, content_hash: str
) -> KnowledgeQueueItem:
    """Map one classified record to a `knowledge_queue` row object (unsaved)."""
    return KnowledgeQueueItem(**_row_values(record, verdict, content_hash))


def _dialect_insert(session):
    """Return an INSERT construct that supports ON CONFLICT for this backend."""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(KnowledgeQueueItem)


def write_verdicts(
    session,
    triples: Iterable[tuple[ChangeRecord, ClassifyResult, str]],
) -> WriteStats:
    """Insert keeper verdicts into `knowledge_queue`, deduped on content_hash.

    Args:
        session: the SQLAlchemy session (caller owns connect/teardown).
        triples: (record, verdict, content_hash) per classified chunk.

    NOISE is dropped. Duplicates are skipped idempotently: identical content
    already queued (or written concurrently by another run) is dropped by
    `ON CONFLICT (content_hash) DO NOTHING`, and duplicates repeated within this
    batch are collapsed first. Commits once at the end.
    """
    triples = list(triples)
    keepers = [(r, v, h) for r, v, h in triples if v.label != "NOISE"]
    dropped_noise = len(triples) - len(keepers)

    # Collapse duplicate content_hash within this batch -- ON CONFLICT only
    # guards against already-committed rows, not duplicates inside one INSERT.
    unique: dict[str, tuple[ChangeRecord, ClassifyResult, str]] = {}
    for record, verdict, content_hash in keepers:
        unique.setdefault(content_hash, (record, verdict, content_hash))

    inserted = 0
    if unique:
        rows = [_row_values(r, v, h) for (r, v, h) in unique.values()]
        stmt = (
            _dialect_insert(session)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(KnowledgeQueueItem.id)
        )
        inserted = len(session.execute(stmt).fetchall())

    session.commit()
    return WriteStats(
        inserted=inserted,
        deduped=len(keepers) - inserted,
        dropped_noise=dropped_noise,
    )


__all__ = [
    "WriteStats",
    "to_queue_item",
    "write_verdicts",
]
