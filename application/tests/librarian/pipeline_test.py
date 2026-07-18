"""Hermetic tests for the C.0->C.4 pipeline (Week 6b).

Every stage is a trivial stub — no DB, embedding model, or cross-encoder.
"""

import unittest
from datetime import datetime, timezone

from application.utils.librarian.pipeline import LibrarianPipeline
from application.utils.librarian.schemas import (
    CreCandidate,
    KnowledgeQueueItem,
    LinkProposal,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
)

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
RUN = "run-7"


def _row(text="Verify the JWT signature.", label="KNOWLEDGE"):
    return KnowledgeQueueItem(
        id="1",
        source_repo="owasp/x",
        source_path="a.md",
        source_commit_sha="abcdef1",
        text=text,
        confidence=0.9,
        llm_label=label,
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
            candidates=[CreCandidate(cre_id="616-305")],
            reranked=[],
            threshold=0.8,
        )


class _Reranker:
    def __init__(self, reranked):
        self._reranked = reranked

    def rerank(self, text, audit):
        return audit.model_copy(update={"reranked": list(self._reranked)})


class _Scaler:
    def __init__(self, conf):
        self._conf = conf

    def confidence(self, logits):
        return self._conf


TOP = [CreCandidate(cre_id="616-305", score_rerank=1.5)]


def _pipeline(rows, reranked, conf):
    return LibrarianPipeline(
        _Source(rows),
        _Retriever(),
        _Reranker(reranked),
        _Scaler(conf),
        threshold=0.8,
        pipeline_run_id=RUN,
    )


class PipelineTest(unittest.TestCase):
    def test_confident_row_auto_links(self):
        result = _pipeline([_row()], TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.linked, 1)
        self.assertEqual(result.stats.review, 0)
        self.assertIsInstance(result.envelopes[0], LinkProposal)
        self.assertEqual(result.envelopes[0].pipeline_run_id, RUN)

    def test_low_confidence_row_reviews_below_threshold(self):
        result = _pipeline([_row()], TOP, 0.4).run(at=AT)
        self.assertEqual(result.stats.review, 1)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.below_threshold)

    def test_empty_shortlist_reviews_no_candidates(self):
        result = _pipeline([_row()], [], 0.95).run(at=AT)
        env = result.envelopes[0]
        self.assertIsInstance(env, ReviewItem)
        self.assertEqual(env.reason_code, ReasonCode.no_candidates)

    def test_uncertain_row_is_skipped_at_boundary(self):
        result = _pipeline([_row(label="UNCERTAIN")], TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.skipped, 1)
        self.assertEqual(result.stats.total, 1)
        self.assertEqual(result.envelopes, [])

    def test_mixed_batch_counts(self):
        rows = [_row(), _row(label="UNCERTAIN"), _row()]
        result = _pipeline(rows, TOP, 0.95).run(at=AT)
        self.assertEqual(result.stats.total, 3)
        self.assertEqual(result.stats.linked, 2)
        self.assertEqual(result.stats.skipped, 1)
        self.assertEqual(len(result.envelopes), 2)


if __name__ == "__main__":
    unittest.main()
