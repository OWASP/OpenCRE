"""Tests for application.utils.noise_filter.pipeline.

In-memory SQLite (create_app(mode="test") + create_all). The LLM is a fake
classifier injected into run_noise_filter, so no real API calls.
"""

from __future__ import annotations

import unittest

from application import create_app, sqla
from application.database.db import HarvestInput, KnowledgeQueueItem
from application.utils.noise_filter.pipeline import run_noise_filter
from application.utils.noise_filter.schemas import ClassifyResult


def _payload(path="document/auth.md", text="security testing content"):
    return {
        "schema_version": "0.2.0",
        "chunk_id": f"chk:{path}",
        "artifact_id": f"art:{path}",
        "pipeline_run_id": "run1",
        "text": text,
        "span": {"index": 0, "total": 1, "heading_path": []},
        "source": {
            "type": "github",
            "repo": "OWASP/test",
            "commit_sha": "abc123",
            "committed_at": "2026-07-17T00:00:00Z",
        },
        "locator": {"kind": "repo_path", "id": path, "path": path},
    }


class _FakeClassifier:
    """Returns preset verdicts; asserts they align with the survivor count."""

    def __init__(self, verdicts):
        self.verdicts = verdicts

    def classify_batch(self, records):
        assert len(records) == len(self.verdicts), (len(records), len(self.verdicts))
        return list(self.verdicts)


def _v(label, conf=0.9):
    return ClassifyResult(label=label, confidence=conf, reasoning="r")


class PipelineTests(unittest.TestCase):

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _add(self, payload, status="pending", run_id="run1"):
        sqla.session.add(
            HarvestInput(pipeline_run_id=run_id, status=status, payload=payload)
        )
        sqla.session.commit()

    def test_happy_path(self) -> None:
        self._add(_payload("document/auth.md"))  # survives -> KNOWLEDGE
        self._add(_payload("frontend/app.css"))  # regex-dropped (NOISE)
        self._add(_payload("document/xss.md"))  # survives -> NOISE
        clf = _FakeClassifier([_v("KNOWLEDGE"), _v("NOISE")])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.read, 3)
        self.assertEqual(s.dropped_noise, 2)  # 1 regex + 1 llm
        self.assertEqual(s.kept_knowledge, 1)
        self.assertEqual(s.inserted, 1)
        self.assertEqual(KnowledgeQueueItem.query.count(), 1)
        # all input rows marked processed
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 0)

    def test_parse_error_marks_row_error(self) -> None:
        bad = _payload()
        del bad["text"]  # violates ChangeRecord (text required)
        self._add(bad)
        clf = _FakeClassifier([])  # no survivors reach the LLM

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual((s.read, s.parse_errors), (1, 1))
        self.assertEqual(HarvestInput.query.filter_by(status="error").count(), 1)
        self.assertEqual(KnowledgeQueueItem.query.count(), 0)

    def test_dry_run_does_not_persist(self) -> None:
        self._add(_payload("document/auth.md"))
        clf = _FakeClassifier([_v("KNOWLEDGE")])

        s = run_noise_filter(sqla.session, "run1", classifier=clf, dry_run=True)

        self.assertEqual(s.kept_knowledge, 1)
        self.assertEqual(s.inserted, 0)
        self.assertEqual(KnowledgeQueueItem.query.count(), 0)
        # row stays pending (dry run mutates nothing)
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 1)

    def test_only_pending_rows_read(self) -> None:
        self._add(_payload("document/auth.md"), status="processed")
        self._add(_payload("document/xss.md"), status="pending")
        clf = _FakeClassifier([_v("KNOWLEDGE")])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.read, 1)
        self.assertEqual(s.inserted, 1)

    def test_run_scoped_by_pipeline_run_id(self) -> None:
        self._add(_payload("document/auth.md"), run_id="run1")
        self._add(_payload("document/xss.md"), run_id="run2")
        clf = _FakeClassifier([_v("KNOWLEDGE")])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.read, 1)
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 1)


if __name__ == "__main__":
    unittest.main()
