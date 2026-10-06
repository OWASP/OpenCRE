from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Iterable, List

from application.defs.cheatsheet_defs import CheatsheetRecord
from application.utils.external_project_parsers.parsers.cheatsheet_record_adapter import (
    section_from_cheatsheet_record,
)
from application.utils.noise_filter.hashing import compute_content_hash
from application.utils.librarian.schemas import (
    KnowledgeQueueItem,
    LocatorKind,
    SCHEMA_VERSION,
    SourceType,
)


def knowledge_queue_item_from_cheatsheet_record(
    record: CheatsheetRecord,
    pipeline_run_id: str,
    llm_label: str = "KNOWLEDGE",
    confidence: float = 1.0,
    llm_reasoning: str | None = None,  ## this field is nullable
) -> KnowledgeQueueItem:
    section = section_from_cheatsheet_record(record)

    return KnowledgeQueueItem(
        id=str(uuid.uuid4()),
        content_hash=compute_content_hash(section.text),
        chunk_id=section.chunk_id,
        artifact_id=section.artifact_id,
        pipeline_run_id=pipeline_run_id,
        schema_version=SCHEMA_VERSION,
        source_type=SourceType.url,
        source_repo=None,
        source_commit_sha=None,
        source_committed_at=section.source.committed_at,
        feed_url=str(section.locator.url),
        post_guid=None,
        locator_kind=LocatorKind.url,
        locator_path=str(section.locator.url),
        span_index=0,
        span_total=1,
        span_heading_path=json.dumps(record.headings) if record.headings else None,
        text=section.text,
        llm_label=llm_label,
        confidence=confidence,
        llm_reasoning=llm_reasoning,
        created_at=datetime.now(timezone.utc),
        consumed_at=None,
    )


def write_knowledge_queue_jsonl(
    records: Iterable[CheatsheetRecord],
    out_path: str,
    pipeline_run_id: str,
    llm_label: str = "KNOWLEDGE",
    confidence: float = 1.0,
    llm_reasoning: str | None = None,
) -> List[KnowledgeQueueItem]:
    items = [
        knowledge_queue_item_from_cheatsheet_record(
            r,
            pipeline_run_id=pipeline_run_id,
            llm_label=llm_label,
            confidence=confidence,
            llm_reasoning=llm_reasoning,
        )
        for r in records
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")
    return items
