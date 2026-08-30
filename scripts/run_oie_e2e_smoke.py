#!/usr/bin/env python3
"""Hermetic OIE A→B→C smoke (no network, no LLM / embedding API).

Seeds a ChangeRecord into harvest_input the way Module A would, runs the
orchestrator with an injected always-KNOWLEDGE Module B classifier and stub
Module C retriever/reranker/scaler, and asserts knowledge_queue was drained
into decision_queue with consumed_at stamped.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    os.environ.setdefault("FLASK_CONFIG", "development")
    os.environ.setdefault("NO_LOAD_GRAPH_DB", "1")

    from application import sqla
    from application.cmd.cre_main import db_connect
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )
    from application.utils.harvester.harvest_writer import write_harvest_input
    from application.utils.harvester.models import IngestChunkRecord, SpanInfo
    from application.utils.harvester.pipeline import RunSummary
    from application.utils.librarian.config_loader import LibrarianConfig
    from application.utils.librarian.envelope_sink import DbEnvelopeSink
    from application.utils.librarian.factory import LibrarianComponents
    from application.utils.librarian.queue_runner import run_librarian_queue
    from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
    from application.utils.noise_filter.pipeline import run_noise_filter
    from application.utils.noise_filter.schemas import ClassifyResult
    from application.utils.oie_orchestrator import run_oie_pipeline

    run_id = "smoke-20260829T000000Z"
    at = datetime(2026, 8, 29, tzinfo=timezone.utc)

    class _FakeClassifier:
        def classify_batch(self, records):
            return [
                ClassifyResult(label="KNOWLEDGE", confidence=0.95, reasoning="smoke")
                for _ in records
            ]

    class _Retriever:
        def retrieve(self, text: str) -> RetrievalAudit:
            return RetrievalAudit(
                retriever="stub/1.0.0",
                candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
                reranked=[],
                threshold=0.0,
            )

    class _Reranker:
        def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit:
            return audit.model_copy(
                update={
                    "reranked": [
                        CreCandidate(cre_id="616-305", score_rerank=20.0),
                    ]
                }
            )

    class _Scaler:
        def confidence(self, logits) -> float:
            return 0.95

    with tempfile.TemporaryDirectory() as tmp:
        cache_db = f"sqlite:///{Path(tmp) / 'smoke.sqlite'}"
        db_connect(cache_db)
        sqla.create_all()

        record = IngestChunkRecord(
            schema_version="0.2.0",
            chunk_id="chk:art:OWASP/ASVS:4.0/en/auth.md:0",
            artifact_id="art:OWASP/ASVS:4.0/en/auth.md",
            pipeline_run_id=run_id,
            text="Use MFA for all admin accounts.",
            span=SpanInfo(
                heading_path=["Authentication"],
                start_line=3,
                end_line=3,
                index=0,
                total=1,
                start_char_idx=0,
                end_char_idx=31,
            ),
            source_type="github",
            source_repo="OWASP/ASVS",
            source_commit_sha="abc1234deadbeef",
            source_committed_at="2026-08-29T00:00:00Z",
            locator_kind="repo_path",
            locator_id="4.0/en/auth.md",
            locator_path="4.0/en/auth.md",
        )
        write_harvest_input(sqla.session, run_id, [record])

        def run_a(session, pipeline_run_id, **kwargs):
            return RunSummary(
                run_id=pipeline_run_id,
                repositories=1,
                chunks_written=1,
                status="ok",
            )

        def run_b(session, pipeline_run_id, **kwargs):
            return run_noise_filter(
                session,
                pipeline_run_id,
                classifier=_FakeClassifier(),
                dry_run=False,
            )

        def run_c(pipeline_run_id, **kwargs):
            cfg = LibrarianConfig(
                crossencoder_model="stub",
                retriever_backend="in_memory",
                top_k_retrieval=20,
                top_k_rerank=5,
                link_threshold=0.80,
                temperature=1.0,
                batch_size=32,
                ece_target=0.10,
                conformal_alpha=0.10,
            )
            components = LibrarianComponents(
                retriever=_Retriever(),
                reranker=_Reranker(),
                scaler=_Scaler(),
                known_cre_ids=frozenset({"616-305"}),
            )
            return run_librarian_queue(
                sqla.session,
                pipeline_run_id,
                components,
                cfg,
                at=at,
                sink=DbEnvelopeSink(sqla.session, pipeline_run_id),
                dry_run=False,
            )

        result = run_oie_pipeline(
            cache_file=cache_db,
            pipeline_run_id=run_id,
            dry_run=False,
            sync_repos=False,
            run_harvester_fn=run_a,
            run_noise_filter_fn=run_b,
            run_librarian_queue_fn=run_c,
        )
        pending = (
            sqla.session.query(HarvestInput)
            .filter_by(pipeline_run_id=run_id, status="pending")
            .count()
        )
        processed = (
            sqla.session.query(HarvestInput)
            .filter_by(pipeline_run_id=run_id, status="processed")
            .count()
        )
        queued = (
            sqla.session.query(KnowledgeQueueItem)
            .filter_by(pipeline_run_id=run_id)
            .count()
        )
        consumed = (
            sqla.session.query(KnowledgeQueueItem)
            .filter(
                KnowledgeQueueItem.pipeline_run_id == run_id,
                KnowledgeQueueItem.consumed_at.isnot(None),
            )
            .count()
        )
        decisions = (
            sqla.session.query(DecisionQueueItem)
            .filter_by(pipeline_run_id=run_id)
            .count()
        )

    out = {
        "orchestrator_ok": result.to_dict()["ok"],
        "harvest_pending": pending,
        "harvest_processed": processed,
        "knowledge_queue_rows": queued,
        "knowledge_consumed": consumed,
        "decision_queue_rows": decisions,
        "stages": result.to_dict()["stages"],
    }
    print(json.dumps(out, indent=2))
    ok = (
        out["orchestrator_ok"]
        and processed >= 1
        and queued >= 1
        and consumed >= 1
        and decisions >= 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
