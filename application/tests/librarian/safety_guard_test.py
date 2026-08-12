"""Tests for the C.4 safety seam.

The behaviour under test is a distinction, not a detector: an unevaluated
verdict must never be readable as a clean one. That is the same failure mode
W5's review caught in the calibration gate, which skipped and still reported
success.
"""

import unittest
from datetime import datetime, timezone

from application.utils.librarian.pipeline import LibrarianPipeline
from application.utils.librarian.safety_guard import NullSafetyGuard, SafetyVerdict
from application.utils.librarian.schemas import (
    CreCandidate,
    KnowledgeQueueItem,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
)

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN = "run-safety"


def _row(row_id: str = "1") -> KnowledgeQueueItem:
    return KnowledgeQueueItem(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:{row_id}",
        artifact_id="art:1",
        pipeline_run_id=RUN,
        schema_version="0.2.0",
        source_type="github",
        source_repo="owasp/x",
        source_commit_sha="abcdef1",
        locator_kind="repo_path",
        locator_path="a.md",
        span_index=0,
        span_total=1,
        text="Verify the JWT signature.",
        llm_label="KNOWLEDGE",
        confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
    )


class _Source:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return iter(self._rows)


class _Retriever:
    def retrieve(self, text):
        return RetrievalAudit(
            retriever="stub",
            candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
            reranked=[],
            threshold=0.0,
        )


class _Reranker:
    def rerank(self, text, audit):
        return audit.model_copy(
            update={"reranked": [CreCandidate(cre_id="616-305", score_rerank=9.0)]}
        )


class _Scaler:
    def confidence(self, logits):
        return 0.99  # comfortably over the bar, so only a flag can block it


class _FlaggingGuard:
    def __init__(self, **flags) -> None:
        self._verdict = SafetyVerdict(evaluated=True, **flags)

    def evaluate(self, section) -> SafetyVerdict:
        return self._verdict


def _run(guard=None):
    return LibrarianPipeline(
        _Source([_row()]),
        _Retriever(),
        _Reranker(),
        _Scaler(),
        threshold=0.8,
        pipeline_run_id=RUN,
        safety_guard=guard,
    ).run(at=AT)


class SafetyVerdictTest(unittest.TestCase):
    def test_default_verdict_is_unevaluated(self) -> None:
        verdict = SafetyVerdict()
        self.assertFalse(verdict.evaluated)
        self.assertFalse(verdict.blocks_auto_link)

    def test_either_flag_blocks(self) -> None:
        self.assertTrue(SafetyVerdict(adversarial=True).blocks_auto_link)
        self.assertTrue(SafetyVerdict(update_ambiguous=True).blocks_auto_link)


class NullSafetyGuardTest(unittest.TestCase):
    def test_reports_that_it_evaluated_nothing(self) -> None:
        verdict = NullSafetyGuard().evaluate(section=None)
        self.assertFalse(verdict.evaluated)
        self.assertFalse(verdict.adversarial)
        self.assertFalse(verdict.update_ambiguous)


class PipelineSafetyWiringTest(unittest.TestCase):
    """#991: `decide()` was called without the flags, so these reason codes
    could never fire from the pipeline. They can now."""

    def test_adversarial_flag_forces_review(self) -> None:
        result = _run(_FlaggingGuard(adversarial=True))
        self.assertEqual(result.stats.linked, 0)
        envelope = result.envelopes[0]
        self.assertIsInstance(envelope, ReviewItem)
        self.assertEqual(envelope.reason_code, ReasonCode.adversarial_flag)

    def test_update_ambiguous_forces_review(self) -> None:
        result = _run(_FlaggingGuard(update_ambiguous=True))
        envelope = result.envelopes[0]
        self.assertIsInstance(envelope, ReviewItem)
        self.assertEqual(envelope.reason_code, ReasonCode.update_ambiguous)

    def test_evaluated_and_clean_still_auto_links(self) -> None:
        result = _run(_FlaggingGuard())
        self.assertEqual(result.stats.linked, 1)
        self.assertEqual(result.stats.safety_unevaluated, 0)

    def test_default_guard_links_but_records_the_gap(self) -> None:
        """Without a guard the row still links — but the run says the safety
        path did not run for it, rather than reporting a clean check."""
        result = _run()
        self.assertEqual(result.stats.linked, 1)
        self.assertEqual(result.stats.safety_unevaluated, 1)


if __name__ == "__main__":
    unittest.main()
