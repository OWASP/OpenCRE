"""Hermetic tests for C.4 — the decision engine (Week 6).

Table-driven over every (confidence, candidates, flag) combination the rule can
see, plus reason-code precedence and the input guards. No key, DB, or model.
"""

import dataclasses
import math
import unittest

from application.utils.librarian.decision_engine import (
    ENGINE_NAME,
    DecisionError,
    DecisionResult,
    decide,
)
from application.utils.librarian.schemas import Decision, ReasonCode

TAU = 0.8
CANDS = ("616-305", "764-507", "611-909")


class DecideTest(unittest.TestCase):
    def test_links_when_confident_and_unflagged(self):
        r = decide(0.95, CANDS, threshold=TAU)
        self.assertEqual(r.decision, Decision.linked)
        self.assertIsNone(r.reason_code)
        self.assertEqual(r.cre_ids, ("616-305",))  # only the top-1 is linked

    def test_confidence_exactly_at_threshold_links(self):
        # link iff confidence >= threshold — the boundary is inclusive.
        r = decide(TAU, CANDS, threshold=TAU)
        self.assertEqual(r.decision, Decision.linked)
        self.assertIsNone(r.reason_code)

    def test_just_below_threshold_reviews(self):
        r = decide(TAU - 1e-9, CANDS, threshold=TAU)
        self.assertEqual(r.decision, Decision.review)
        self.assertEqual(r.reason_code, ReasonCode.below_threshold)
        self.assertEqual(r.cre_ids, ("616-305",))  # best-guess suggestion kept

    def test_no_candidates_reviews_even_when_confident(self):
        r = decide(0.99, (), threshold=TAU)
        self.assertEqual(r.decision, Decision.review)
        self.assertEqual(r.reason_code, ReasonCode.no_candidates)
        self.assertEqual(r.cre_ids, ())  # nothing to suggest

    def test_adversarial_flag_reviews_even_when_confident(self):
        r = decide(0.99, CANDS, threshold=TAU, adversarial=True)
        self.assertEqual(r.decision, Decision.review)
        self.assertEqual(r.reason_code, ReasonCode.adversarial_flag)

    def test_update_ambiguous_flag_reviews_even_when_confident(self):
        r = decide(0.99, CANDS, threshold=TAU, update_ambiguous=True)
        self.assertEqual(r.decision, Decision.review)
        self.assertEqual(r.reason_code, ReasonCode.update_ambiguous)

    def test_precedence_no_candidates_beats_everything(self):
        # empty shortlist + a flag + high confidence -> still NO_CANDIDATES.
        r = decide(0.99, (), threshold=TAU, adversarial=True, update_ambiguous=True)
        self.assertEqual(r.reason_code, ReasonCode.no_candidates)

    def test_precedence_adversarial_beats_below_threshold(self):
        r = decide(0.10, CANDS, threshold=TAU, adversarial=True)
        self.assertEqual(r.reason_code, ReasonCode.adversarial_flag)

    def test_precedence_adversarial_beats_update_ambiguous(self):
        r = decide(0.99, CANDS, threshold=TAU, adversarial=True, update_ambiguous=True)
        self.assertEqual(r.reason_code, ReasonCode.adversarial_flag)

    def test_confidence_is_carried_through(self):
        for conf in (0.0, 0.42, 0.8, 1.0):
            self.assertEqual(decide(conf, CANDS, threshold=TAU).confidence, conf)


class GuardTest(unittest.TestCase):
    def test_bad_threshold_rejected(self):
        for bad in (-0.1, 1.1, math.nan, math.inf):
            with self.assertRaises(DecisionError):
                decide(0.5, CANDS, threshold=bad)

    def test_bad_confidence_rejected(self):
        for bad in (-0.1, 1.1, math.nan, math.inf):
            with self.assertRaises(DecisionError):
                decide(bad, CANDS, threshold=TAU)


class ResultTest(unittest.TestCase):
    def test_engine_name_is_versioned(self):
        self.assertRegex(ENGINE_NAME, r"^decision-engine/\d+\.\d+\.\d+$")

    def test_result_is_frozen(self):
        r = decide(0.95, CANDS, threshold=TAU)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.confidence = 0.1  # type: ignore[misc]


class SourceLabelDoesNotChangeTheRuleTest(unittest.TestCase):
    """B's label is not an input to the decision.

    A chunk B forwarded as UNCERTAIN is decided on the same evidence as a
    KNOWLEDGE one. C's confidence is calibrated on its own terms, and holding
    back a chunk that scored 0.99 on an upstream doubt would bury reviewers in
    obvious matches. Provenance is preserved on the row instead
    (``decision_queue.source_label``), so a consumer can still weigh them apart.
    """

    def test_decide_takes_no_source_label_argument(self) -> None:
        import inspect

        params = inspect.signature(decide).parameters

        self.assertNotIn("source_uncertain", params)
        self.assertEqual(
            [p for p in params if p not in ("confidence", "candidate_cre_ids")],
            ["threshold", "adversarial", "update_ambiguous"],
        )

    def test_a_confident_chunk_links_whatever_its_source(self) -> None:
        self.assertEqual(
            decide(0.99, ["616-305"], threshold=0.80).decision, Decision.linked
        )

    def test_a_weak_chunk_reviews_whatever_its_source(self) -> None:
        result = decide(0.40, ["616-305"], threshold=0.80)

        self.assertEqual(result.decision, Decision.review)
        self.assertEqual(result.reason_code, ReasonCode.below_threshold)


if __name__ == "__main__":
    unittest.main()
