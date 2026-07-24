"""Tests for application.utils.noise_filter.queue_writer.

Uses an in-memory SQLite DB (create_app(mode="test") + create_all), matching
the project's db_test.py pattern. No migration needed.
"""

from __future__ import annotations

import json
import unittest

from application import create_app, sqla
from application.database.db import KnowledgeQueueItem
from application.utils.noise_filter.queue_writer import write_verdicts
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult


def _record(chunk_id="chk", source=None, heading_path=None) -> ChangeRecord:
    return ChangeRecord.model_validate(
        {
            "schema_version": "0.2.0",
            "chunk_id": chunk_id,
            "artifact_id": "art:test",
            "pipeline_run_id": "run1",
            "text": "some security text",
            "span": {"index": 0, "total": 1, "heading_path": heading_path or []},
            "source": source
            or {
                "type": "github",
                "repo": "OWASP/test",
                "commit_sha": "abc123",
                "committed_at": "2026-07-17T00:00:00Z",
            },
            "locator": {"kind": "repo_path", "id": "p.md", "path": "p.md"},
        }
    )


def _verdict(label="KNOWLEDGE", conf=0.9) -> ClassifyResult:
    return ClassifyResult(label=label, confidence=conf, reasoning="because")


class QueueWriterTests(unittest.TestCase):

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_noise_dropped_keepers_written(self) -> None:
        triples = [
            (_record("a"), _verdict("KNOWLEDGE"), "h1"),
            (_record("b"), _verdict("NOISE"), "h2"),
            (_record("c"), _verdict("UNCERTAIN", 0.0), "h3"),
        ]
        stats = write_verdicts(sqla.session, triples)
        self.assertEqual((stats.inserted, stats.dropped_noise), (2, 1))
        labels = sorted(r.llm_label for r in KnowledgeQueueItem.query.all())
        self.assertEqual(labels, ["KNOWLEDGE", "UNCERTAIN"])

    def test_dedup_within_batch(self) -> None:
        triples = [
            (_record("a"), _verdict(), "same"),
            (_record("b"), _verdict(), "same"),
        ]
        stats = write_verdicts(sqla.session, triples)
        self.assertEqual((stats.inserted, stats.deduped), (1, 1))
        self.assertEqual(KnowledgeQueueItem.query.count(), 1)

    def test_dedup_against_existing_rows(self) -> None:
        write_verdicts(sqla.session, [(_record("a"), _verdict(), "h1")])
        stats = write_verdicts(sqla.session, [(_record("b"), _verdict(), "h1")])
        self.assertEqual((stats.inserted, stats.deduped), (0, 1))
        self.assertEqual(KnowledgeQueueItem.query.count(), 1)

    def test_github_source_columns(self) -> None:
        write_verdicts(
            sqla.session, [(_record("a", heading_path=["Auth"]), _verdict(), "h1")]
        )
        row = KnowledgeQueueItem.query.first()
        self.assertEqual(row.source_type, "github")
        self.assertEqual(row.source_repo, "OWASP/test")
        self.assertEqual(row.source_commit_sha, "abc123")
        self.assertIsNone(row.feed_url)
        self.assertEqual(json.loads(row.span_heading_path), ["Auth"])

    def test_rss_source_columns(self) -> None:
        rss = {
            "type": "rss",
            "feed_url": "https://example.org/feed.xml",
            "post_guid": "guid-123",
        }
        write_verdicts(sqla.session, [(_record("a", source=rss), _verdict(), "h1")])
        row = KnowledgeQueueItem.query.first()
        self.assertEqual(row.source_type, "rss")
        self.assertEqual(row.feed_url, "https://example.org/feed.xml")
        self.assertEqual(row.post_guid, "guid-123")
        self.assertIsNone(row.source_repo)


if __name__ == "__main__":
    unittest.main()
