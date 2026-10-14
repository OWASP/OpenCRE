"""Tests for relative margin cutoff (CRE_LIBRARIAN_MARGIN_GAMMA)."""

from __future__ import annotations

import unittest

from application.utils.librarian.margin_cutoff import (
    apply_margin_gamma,
    apply_margin_gamma_ids,
)
from application.utils.librarian.schemas import CreCandidate


class MarginCutoffTest(unittest.TestCase):
    def test_keeps_rank1_always(self) -> None:
        cands = [
            CreCandidate(cre_id="a", score_rerank=1.0),
            CreCandidate(cre_id="b", score_rerank=0.50),
        ]
        out = apply_margin_gamma(cands, gamma=0.85)
        self.assertEqual([c.cre_id for c in out], ["a"])

    def test_keeps_near_ties(self) -> None:
        cands = [
            CreCandidate(cre_id="a", score_rerank=1.0),
            CreCandidate(cre_id="b", score_rerank=0.90),
            CreCandidate(cre_id="c", score_rerank=0.70),
        ]
        out = apply_margin_gamma(cands, gamma=0.85)
        self.assertEqual([c.cre_id for c in out], ["a", "b"])

    def test_ids_variant(self) -> None:
        ids = apply_margin_gamma_ids(
            ["a", "b", "c"],
            {"a": 1.0, "b": 0.84, "c": 0.90},
            gamma=0.85,
        )
        self.assertEqual(ids, ["a", "c"])

    def test_empty_shortlist(self) -> None:
        self.assertEqual(apply_margin_gamma([], gamma=0.85), [])


if __name__ == "__main__":
    unittest.main()
