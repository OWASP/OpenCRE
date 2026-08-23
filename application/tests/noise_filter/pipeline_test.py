"""Tests for application.utils.noise_filter.pipeline.

In-memory SQLite (create_app(mode="test") + create_all). The LLM is a fake
classifier injected into run_noise_filter, so no real API calls.
"""

from __future__ import annotations

import unittest

from application import create_app, sqla
from application.database.db import HarvestInput, KnowledgeQueueItem
from application.utils.noise_filter.config_loader import NoiseFilterConfig
from application.utils.noise_filter.hashing import compute_content_hash
from application.utils.noise_filter.llm_classifier import (
    LLM_CALL_FAILED,
    MALFORMED_OUTPUT,
)
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


def _infra():
    """The fallback verdict B emits when the LLM call itself fails (retryable)."""
    return ClassifyResult(
        label="UNCERTAIN", confidence=0.0, reasoning=LLM_CALL_FAILED, retryable=True
    )


def _malformed():
    """The fallback verdict for unparseable model output (persisted, not retried)."""
    return ClassifyResult(label="UNCERTAIN", confidence=0.0, reasoning=MALFORMED_OUTPUT)


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

    def test_misaligned_verdicts_raise_and_persist_nothing(self) -> None:
        self._add(_payload("document/auth.md"))
        self._add(_payload("document/xss.md"))

        class _ShortClassifier:  # returns fewer verdicts than survivors
            def classify_batch(self, records):
                return [_v("KNOWLEDGE")]

        with self.assertRaises(RuntimeError):
            run_noise_filter(sqla.session, "run1", classifier=_ShortClassifier())
        # nothing written, no rows marked processed
        self.assertEqual(KnowledgeQueueItem.query.count(), 0)
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 2)

    def test_infra_failure_leaves_row_pending(self) -> None:
        # One chunk classifies, the other hit an LLM-call failure. The failed one
        # is not written and its row stays `pending` for a retry; the run is still
        # "ok" because not the whole batch failed (rate 0.5 < threshold 1.0).
        self._add(_payload("document/auth.md"))  # -> KNOWLEDGE
        self._add(_payload("document/xss.md"))  # -> infra failure
        clf = _FakeClassifier([_v("KNOWLEDGE"), _infra()])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.retry_pending, 1)
        self.assertEqual(s.kept_knowledge, 1)
        self.assertEqual(s.inserted, 1)
        self.assertEqual(s.status, "ok")
        self.assertEqual(KnowledgeQueueItem.query.count(), 1)
        # exactly one row still pending (the infra-failed one); the other processed
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 1)
        self.assertEqual(HarvestInput.query.filter_by(status="processed").count(), 1)

    def test_total_infra_failure_is_degraded(self) -> None:
        # Every classified chunk failed -> status degraded (rate 1.0), nothing
        # written, both rows left pending for the orchestrator to retry.
        self._add(_payload("document/auth.md"))
        self._add(_payload("document/xss.md"))
        clf = _FakeClassifier([_infra(), _infra()])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.retry_pending, 2)
        self.assertEqual(s.status, "degraded")
        self.assertEqual(s.inserted, 0)
        self.assertEqual(KnowledgeQueueItem.query.count(), 0)
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 2)

    def test_clean_run_not_degraded_at_threshold_zero(self) -> None:
        # A `failure_threshold` of 0.0 must NOT degrade a clean run: with no infra
        # failures there is nothing to retry, so status stays `ok`.
        self._add(_payload("document/auth.md"))
        clf = _FakeClassifier([_v("KNOWLEDGE")])
        cfg = NoiseFilterConfig(failure_threshold=0.0)

        s = run_noise_filter(sqla.session, "run1", config=cfg, classifier=clf)

        self.assertEqual(s.retry_pending, 0)
        self.assertEqual(s.status, "ok")

    def test_one_infra_failure_degraded_at_threshold_zero(self) -> None:
        # At threshold 0.0 a single infra failure is enough to degrade the run.
        self._add(_payload("document/auth.md"))
        self._add(_payload("document/xss.md"))
        clf = _FakeClassifier([_v("KNOWLEDGE"), _infra()])
        cfg = NoiseFilterConfig(failure_threshold=0.0)

        s = run_noise_filter(sqla.session, "run1", config=cfg, classifier=clf)

        self.assertEqual(s.retry_pending, 1)
        self.assertEqual(s.status, "degraded")

    def test_malformed_output_is_persisted_not_retried(self) -> None:
        # Unparseable output is a genuine UNCERTAIN row: written and finalized,
        # never left pending (retrying junk would loop forever).
        self._add(_payload("document/auth.md"))
        clf = _FakeClassifier([_malformed()])

        s = run_noise_filter(sqla.session, "run1", classifier=clf)

        self.assertEqual(s.retry_pending, 0)
        self.assertEqual(s.kept_uncertain, 1)
        self.assertEqual(s.inserted, 1)
        self.assertEqual(s.status, "ok")
        self.assertEqual(HarvestInput.query.filter_by(status="pending").count(), 0)

    def test_sanitize_is_llm_input_only(self) -> None:
        # The "ﬀ" ligature is sanitized to "ff" for the LLM, but the queue keeps
        # the original text and hashes the original (stable dedup key).
        original = "oﬀice hardening steps"
        self._add(_payload("document/lig.md", text=original))
        seen = {}

        class _Capture:
            def classify_batch(self, records):
                seen["text"] = records[0].text
                return [_v("KNOWLEDGE")]

        run_noise_filter(sqla.session, "run1", classifier=_Capture())

        self.assertEqual(seen["text"], "office hardening steps")  # LLM saw sanitized
        row = KnowledgeQueueItem.query.first()
        self.assertEqual(row.text, original)  # queue kept the canonical original
        self.assertEqual(row.content_hash, compute_content_hash(original))


if __name__ == "__main__":
    unittest.main()
