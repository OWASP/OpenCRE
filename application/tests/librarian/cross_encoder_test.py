"""Tests for the C.2 cross-encoder reranker (Week 4).

Hermetic: the cross-encoder score function and the CRE text map are injected as
controlled values, so re-ordering, top-N truncation, tie stability, the audit
shape, and the failure modes are all assertable without torch, an LLM, or a DB.
"""

import unittest

from application.utils.librarian.cross_encoder import (
    CrossEncoderReranker,
    MissingCandidateTextError,
    RerankerError,
)
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

# The text each candidate CRE is scored against (its embeddings_content).
CRE_TEXTS = {
    "111-111": "text-a",
    "222-222": "text-b",
    "333-333": "text-c",
}


def make_audit(threshold=0.8):
    """A C.1 shortlist in cosine order: a (0.90) > b (0.80) > c (0.70)."""
    return RetrievalAudit(
        retriever="in-memory-cosine/0.1.0",
        candidates=[
            CreCandidate(cre_id="111-111", score_vector=0.90),
            CreCandidate(cre_id="222-222", score_vector=0.80),
            CreCandidate(cre_id="333-333", score_vector=0.70),
        ],
        reranked=[],
        threshold=threshold,
    )


# The cross-encoder disagrees with cosine: it likes b most, then c, then a.
_PAIR_SCORES = {
    ("q", "text-a"): 0.10,
    ("q", "text-b"): 0.90,
    ("q", "text-c"): 0.50,
}


def fake_score(pairs):
    return [_PAIR_SCORES[(q, cand)] for q, cand in pairs]


def make_reranker(top_n=5, cre_texts=None, score_fn=fake_score):
    return CrossEncoderReranker(
        score_fn=score_fn,
        top_n=top_n,
        cre_texts=CRE_TEXTS if cre_texts is None else cre_texts,
    )


class RerankTest(unittest.TestCase):
    def test_reranks_by_cross_encoder_score_not_cosine(self) -> None:
        audit = make_reranker().rerank("q", make_audit())
        # Cosine order was a,b,c; the cross-encoder reorders to b,c,a.
        self.assertEqual(
            [c.cre_id for c in audit.reranked], ["222-222", "333-333", "111-111"]
        )
        scores = [c.score_rerank for c in audit.reranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertAlmostEqual(audit.reranked[0].score_rerank, 0.90)

    def test_candidates_preserved_and_audit_shape(self) -> None:
        audit = make_reranker().rerank("q", make_audit(threshold=0.8))
        # candidates[] (the pre-rerank shortlist) is untouched, still cosine order.
        self.assertEqual(
            [c.cre_id for c in audit.candidates], ["111-111", "222-222", "333-333"]
        )
        # score_rerank is only set on reranked[], never on candidates[].
        self.assertTrue(all(c.score_rerank is None for c in audit.candidates))
        self.assertEqual(audit.retriever, "in-memory-cosine/0.1.0")
        self.assertEqual(audit.threshold, 0.8)

    def test_top_n_truncates_to_best(self) -> None:
        audit = make_reranker(top_n=2).rerank("q", make_audit())
        self.assertEqual([c.cre_id for c in audit.reranked], ["222-222", "333-333"])

    def test_top_n_larger_than_shortlist_keeps_all(self) -> None:
        audit = make_reranker(top_n=20).rerank("q", make_audit())
        self.assertEqual(len(audit.reranked), 3)

    def test_ties_preserve_cosine_order(self) -> None:
        # Equal cross-encoder scores -> the stable sort keeps C.1's cosine order.
        audit = make_reranker(score_fn=lambda pairs: [1.0] * len(pairs)).rerank(
            "q", make_audit()
        )
        self.assertEqual(
            [c.cre_id for c in audit.reranked], ["111-111", "222-222", "333-333"]
        )

    def test_empty_candidates_yields_empty_reranked(self) -> None:
        empty = RetrievalAudit(
            retriever="r", candidates=[], reranked=[], threshold=0.8
        )
        out = make_reranker().rerank("q", empty)
        self.assertEqual(out.reranked, [])


class FailureModeTest(unittest.TestCase):
    def test_missing_cre_text_raises(self) -> None:
        with self.assertRaises(MissingCandidateTextError):
            make_reranker(cre_texts={"111-111": "text-a"}).rerank("q", make_audit())

    def test_non_positive_top_n_rejected(self) -> None:
        with self.assertRaises(RerankerError):
            make_reranker(top_n=0)

    def test_score_count_mismatch_rejected(self) -> None:
        with self.assertRaises(RerankerError):
            make_reranker(score_fn=lambda pairs: [0.5]).rerank("q", make_audit())


if __name__ == "__main__":
    unittest.main()
