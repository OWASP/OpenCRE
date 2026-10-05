#!/usr/bin/env python

"""Cheat Sheet → CheatsheetRecord → knowledge_queue JSONL → FixtureKnowledgeSource → Module C dry-run.

Uses real Cheat Sheet extraction and the new CheatsheetRecord ->
knowledge_queue boundary, then runs the real Librarian C.0-C.4 pipeline
using the existing dry-run C.1/C.2 setup.
"""

import os
import sys
from datetime import datetime, timezone


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)


from application.utils.external_project_parsers.parsers.cheatsheet_extractor import (
    extract_cheatsheet_record,
)
from application.utils.external_project_parsers.parsers.cheatsheet_knowledge_queue_item import (
    write_knowledge_queue_jsonl,
)
from application.utils.librarian.candidate_retriever import (
    CandidatePool,
    CandidateRetriever,
)
from application.utils.librarian.cross_encoder import CrossEncoderReranker
from application.utils.librarian.knowledge_source import FixtureKnowledgeSource
from application.utils.librarian.pipeline import LibrarianPipeline
from application.utils.librarian.safety_guard import NullSafetyGuard
from application.utils.librarian.schemas import LinkProposal
from scripts.cheatsheet_dry_run import (
    build_pipeline,
    load_fixtures,
)

TOP_K_RETRIEVAL = 5
TOP_K_RERANK = 3
DECISION_THRESHOLD = 0.80

PIPELINE_RUN_ID = "run-cheatsheet-knowledge-queue-dryrun"

FIXTURES_DIR = os.path.join(
    REPO_ROOT,
    "application",
    "tests",
    "librarian",
    "fixtures",
    "cheatsheets",
)

KNOWLEDGE_QUEUE_PATH = os.path.join(
    REPO_ROOT,
    "application",
    "tests",
    "librarian",
    "fixtures",
    "sample_cheatsheets_knowledge_queue.jsonl",
)

class StubScaler:
    """Deterministic C.3 confidence for the dry-run."""

    def confidence(self, logits):
        # Above the C.4 threshold, so the LinkProposal path can be exercised.
        return 0.95

def build_knowledge_queue():
    """Extract every fixture into a CheatsheetRecord and write the queue JSONL."""

    records = []

    for markdown, source_path in load_fixtures(FIXTURES_DIR):
        filename = os.path.basename(source_path)

        print("=" * 72)
        print(f"CHEAT SHEET: {filename}")

        try:
            record = extract_cheatsheet_record(
                markdown,
                source_path,
            )

            # Local fixture files may not have a committed_at value.
            # Keep the same fallback used by cheatsheet_dry_run.py 
            if not record.metadata.get("committed_at"):
                record.metadata["committed_at"] = (
                    "2026-01-01T00:00:00+00:00"
                )

            records.append(record)

            print(f"Record title : {record.title}")
            print("Record       : extracted successfully")

        except Exception as exc:
            print(f"❌ extraction failed: {exc}")
            raise

    if not records:
        raise RuntimeError(
            f"No Cheat Sheet fixtures found in {FIXTURES_DIR}"
        )

    print("\n" + "=" * 72)
    print("WRITING KNOWLEDGE QUEUE")
    print("=" * 72)

    items = write_knowledge_queue_jsonl(
        records,
        KNOWLEDGE_QUEUE_PATH,
        pipeline_run_id=PIPELINE_RUN_ID,
    )

    print(f"Records      : {len(records)}")
    print(f"Queue rows   : {len(items)}")
    print(f"Output       : {KNOWLEDGE_QUEUE_PATH}")

    return records, items


def main():
    print("=" * 72)
    print("CHEAT SHEET -> KNOWLEDGE QUEUE -> MODULE C DRY-RUN")
    print("=" * 72)

    print("\nUsing:")
    print("  • real CheatSheetRecord extraction")
    print("  • real CheatsheetRecord -> knowledge_queue mapping")
    print("  • real JSONL -> FixtureKnowledgeSource boundary")
    print("  • real LibrarianPipeline")
    print("  • real C.0 -> C.4 pipeline")
    print("  • controlled local embeddings")
    print("  • existing CrossEncoder reranking")
    print("  • deterministic C.3 confidence")
    print()

    build_knowledge_queue()

    print("\n" + "=" * 72)
    print("RUNNING LIBRARIAN C.0-C.4")
    print("=" * 72)

    retriever, reranker = build_pipeline()

    pipeline = LibrarianPipeline(
        source=FixtureKnowledgeSource(KNOWLEDGE_QUEUE_PATH),
        retriever=retriever,
        reranker=reranker,
        scaler=StubScaler(),
        threshold=DECISION_THRESHOLD,
        pipeline_run_id=PIPELINE_RUN_ID,
        safety_guard=NullSafetyGuard(),
    )

    result = pipeline.run(
        at=datetime.now(timezone.utc),
    )

    print("\n" + "=" * 72)
    print("DRY-RUN RESULT")
    print("=" * 72)

    print("Stats:", result.stats)

    for envelope in result.envelopes:
        kind = (
            "LinkProposal"
            if isinstance(envelope, LinkProposal)
            else "ReviewItem"
        )

        print(f"\n{kind}")
        print("  chunk_id    :", envelope.chunk_id)
        print("  artifact_id :", envelope.artifact_id)
        print("  source.type :", envelope.knowledge.source.type)
        print("  source.url  :", envelope.knowledge.source.url)
        print("  locator.kind:", envelope.knowledge.locator.kind)
        print("  locator.url :", envelope.knowledge.locator.url)

    print("\n" + "=" * 72)
    print("✅ DRY-RUN COMPLETED")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())