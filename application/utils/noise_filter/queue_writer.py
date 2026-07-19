"""Module B output stage: write classified chunks to `knowledge_queue`.

This is Module B's DB boundary. It maps a (ChangeRecord, ClassifyResult,
content_hash) triple into a `KnowledgeQueueItem` row and inserts the keepers,
deduped on `content_hash`. NOISE verdicts are dropped (they never reach the
queue); KNOWLEDGE and UNCERTAIN are written (UNCERTAIN is for Module D's HITL
review). Module C reads from `knowledge_queue`; see module_c_contract.md (v0.2).

The classifier and schemas stay DB-free by design; this module is the only
part of Module B that imports the SQLAlchemy layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from application.database.db import KnowledgeQueueItem
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult


@dataclass(frozen=True)
class WriteStats:
    """Outcome of writing a batch of verdicts to the queue."""

    inserted: int = 0
    deduped: int = 0
    dropped_noise: int = 0


def to_queue_item(
    record: ChangeRecord, verdict: ClassifyResult, content_hash: str
) -> KnowledgeQueueItem:
    """Map one classified record to a `knowledge_queue` row (unsaved)."""
    source = record.source
    item = KnowledgeQueueItem(
        content_hash=content_hash,
        chunk_id=record.chunk_id,
        artifact_id=record.artifact_id,
        pipeline_run_id=record.pipeline_run_id,
        schema_version=record.schema_version,
        source_type=source.type,
        locator_kind=record.locator.kind,
        locator_path=record.locator.path,
        span_index=record.span.index,
        span_total=record.span.total,
        span_heading_path=json.dumps(record.span.heading_path),
        text=record.text,
        llm_label=verdict.label,
        confidence=verdict.confidence,
        llm_reasoning=verdict.reasoning,
    )
    if source.type == "github":
        item.source_repo = source.repo
        item.source_commit_sha = source.commit_sha
        item.source_committed_at = source.committed_at
    elif source.type == "rss":
        item.feed_url = source.feed_url
        item.post_guid = source.post_guid
    return item


def write_verdicts(
    session,
    triples: Iterable[tuple[ChangeRecord, ClassifyResult, str]],
) -> WriteStats:
    """Insert keeper verdicts into `knowledge_queue`, deduped on content_hash.

    Args:
        session: the SQLAlchemy session (caller owns connect/teardown).
        triples: (record, verdict, content_hash) per classified chunk.

    NOISE is dropped. Duplicates (same content_hash already queued, or repeated
    within this batch) are skipped. Commits once at the end.
    """
    triples = list(triples)
    keepers = [(r, v, h) for r, v, h in triples if v.label != "NOISE"]
    dropped_noise = len(triples) - len(keepers)

    # Content hashes already present in the queue (single query, not per-row).
    candidate_hashes = {h for _, _, h in keepers}
    existing: set[str] = set()
    if candidate_hashes:
        rows = (
            session.query(KnowledgeQueueItem.content_hash)
            .filter(KnowledgeQueueItem.content_hash.in_(candidate_hashes))
            .all()
        )
        existing = {row[0] for row in rows}

    seen: set[str] = set()
    inserted = 0
    deduped = 0
    for record, verdict, content_hash in keepers:
        if content_hash in existing or content_hash in seen:
            deduped += 1
            continue
        seen.add(content_hash)
        session.add(to_queue_item(record, verdict, content_hash))
        inserted += 1

    session.commit()
    return WriteStats(inserted=inserted, deduped=deduped, dropped_noise=dropped_noise)


__all__ = [
    "WriteStats",
    "to_queue_item",
    "write_verdicts",
]
