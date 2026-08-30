import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from application import create_app, sqla
from application.database.db import HarvestInput
from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
from application.utils.harvester.harvest_writer import write_harvest_input
from application.utils.harvester.models import (
    Document,
    HeadingNode,
    IngestChunkRecord,
    Locator,
    SourceInfo,
    SpanInfo,
)
from application.utils.harvester.schemas import ChunkingConfig
from application.utils.noise_filter.schemas import ChangeRecord
from application.utils.oie_orchestrator import run_oie_pipeline


class HarvestWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def test_writes_pending_change_records(self) -> None:
        record = IngestChunkRecord(
            schema_version="0.2.0",
            chunk_id="chk:art:OWASP/ASVS:a.md:0",
            artifact_id="art:OWASP/ASVS:a.md",
            pipeline_run_id="run-xyz",
            text="Authentication should use MFA",
            span=SpanInfo(
                heading_path=["Auth"],
                start_line=1,
                end_line=1,
                index=0,
                total=1,
                start_char_idx=0,
                end_char_idx=30,
            ),
            source_type="github",
            source_repo="OWASP/ASVS",
            source_commit_sha="abc1234deadbeef",
            source_committed_at="2026-02-01T01:00:00Z",
            locator_kind="repo_path",
            locator_id="a.md",
            locator_path="a.md",
        )
        written = write_harvest_input(sqla.session, "run-xyz", [record])
        self.assertEqual(written, 1)
        row = sqla.session.query(HarvestInput).one()
        self.assertEqual(row.pipeline_run_id, "run-xyz")
        self.assertEqual(row.status, "pending")
        ChangeRecord.model_validate(row.payload)
        self.assertEqual(row.payload["pipeline_run_id"], "run-xyz")


class DocumentChunkPipelineIntegrationTests(unittest.TestCase):
    def test_emits_valid_change_records(self) -> None:
        text = "# Auth\n\nUse MFA everywhere.\n"
        document = Document(
            schema_version="0.2.0",
            artifact_id="art:OWASP/ASVS:auth.md",
            pipeline_run_id="run-1",
            text=text,
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha="abc1234deadbeef",
                committed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            ),
            locator=Locator(kind="repo_path", id="auth.md", path="auth.md"),
            heading_structure=[
                HeadingNode(level=1, text="Auth", start_line=1, end_line=3)
            ],
        )
        pipeline = DocumentChunkPipeline(
            chunking=ChunkingConfig(
                strategy="markdown_heading", max_tokens=200, overlap_tokens=10
            )
        )
        records = pipeline.chunk(document)
        self.assertGreaterEqual(len(records), 1)
        for record in records:
            ChangeRecord.model_validate(
                {
                    "schema_version": record.schema_version,
                    "chunk_id": record.chunk_id,
                    "artifact_id": record.artifact_id,
                    "pipeline_run_id": record.pipeline_run_id,
                    "text": record.text,
                    "span": {
                        "index": record.span.index,
                        "total": record.span.total,
                        "heading_path": record.span.heading_path,
                        "start_char_idx": record.span.start_char_idx,
                        "end_char_idx": record.span.end_char_idx,
                        "start_line": record.span.start_line,
                        "end_line": record.span.end_line,
                    },
                    "source": {
                        "type": record.source_type,
                        "repo": record.source_repo,
                        "commit_sha": record.source_commit_sha,
                        "committed_at": record.source_committed_at,
                    },
                    "locator": {
                        "kind": record.locator_kind,
                        "id": record.locator_id,
                        "path": record.locator_path,
                    },
                }
            )


class OieOrchestratorTests(unittest.TestCase):
    def test_sequences_a_b_c_and_stops_on_a_error(self) -> None:
        a_calls = []

        def run_a(session, run_id, **kwargs):
            a_calls.append(run_id)
            summary = Mock()
            summary.status = "degraded"
            summary.to_json.return_value = '{"status":"degraded"}'
            return summary

        b_calls = []

        def run_b(session, run_id, **kwargs):
            b_calls.append(run_id)
            summary = Mock()
            summary.status = "ok"
            summary.to_json.return_value = '{"status":"ok"}'
            return summary

        result = run_oie_pipeline(
            cache_file="sqlite://",
            pipeline_run_id="run-1",
            dry_run=True,
            sync_repos=False,
            run_harvester_fn=run_a,
            run_noise_filter_fn=run_b,
            run_librarian_queue_fn=lambda *a, **k: {"ok": True},
        )
        self.assertEqual(a_calls, ["run-1"])
        self.assertEqual(b_calls, [])
        self.assertFalse(result.to_dict()["ok"])
        self.assertEqual(result.stages[0].status, "error")

    def test_runs_all_stages_when_ok(self) -> None:
        def ok_summary(*args, **kwargs):
            summary = Mock()
            summary.status = "ok"
            summary.to_json.return_value = '{"status":"ok"}'
            return summary

        result = run_oie_pipeline(
            cache_file="sqlite://",
            pipeline_run_id="run-2",
            dry_run=True,
            sync_repos=False,
            run_harvester_fn=ok_summary,
            run_noise_filter_fn=ok_summary,
            run_librarian_queue_fn=lambda *a, **k: {"status": "ok"},
        )
        self.assertTrue(result.to_dict()["ok"])
        self.assertEqual(
            [s.name for s in result.stages],
            [
                "module_a_harvester",
                "module_b_noise_filter",
                "module_c_librarian",
            ],
        )


if __name__ == "__main__":
    unittest.main()
