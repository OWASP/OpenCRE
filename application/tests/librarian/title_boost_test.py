"""Tests for title ↔ CRE lexical boost."""

import unittest

from application.utils.librarian.title_boost import (
    apply_title_boost,
    title_overlap_boost,
)


class TitleBoostTest(unittest.TestCase):
    def test_overlap_prefers_matching_name(self) -> None:
        q = "Section: Broken Access Control\n\nBody"
        a = title_overlap_boost(q, "Use a centralized access control mechanism")
        b = title_overlap_boost(q, "Encrypt data at rest with AES")
        self.assertGreater(a, b)

    def test_apply_reorders_ties(self) -> None:
        q = "Section: Broken Access Control\n"
        scores = [1.0, 1.0]
        texts = [
            "Encrypt data at rest",
            "Limit authorize access control functionality",
        ]
        out = apply_title_boost(q, scores, texts, weight=2.0)
        self.assertGreater(out[1], out[0])

    def test_hybrid_keeps_strong_vector(self) -> None:
        from application.utils.librarian.title_boost import hybrid_rank_scores

        scores = hybrid_rank_scores(
            vectors=[0.9, 0.5],
            ce_scores=[-9.0, 5.0],
            title_boosts=[0.8, 0.0],
            alpha=1.0,
            beta=3.0,
            gamma=0.15,
        )
        self.assertGreater(scores[0], scores[1])


if __name__ == "__main__":
    unittest.main()
