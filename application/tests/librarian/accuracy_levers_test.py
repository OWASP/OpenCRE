"""Unit tests for experimental accuracy levers (stub LLM — no network)."""

from __future__ import annotations

import os
import unittest

from application.utils.librarian.coverage_fail_closed import coverage_is_thin
from application.utils.librarian.crosswalk_cage import apply_crosswalk_cage
from application.utils.librarian.fail_closed_batch import (
    evaluate_fail_closed_levers,
    parse_batched_fail_closed,
)
from application.utils.librarian.pairwise_vote import (
    parse_pairwise_vote,
    pairwise_blocks_auto_link,
)
from application.utils.librarian.schemas import CreCandidate, ReasonCode, RetrievalAudit
from application.utils.librarian.source_grounding import (
    grounding_blocks_auto_link,
    parse_grounding_verdict,
)


class PairwiseVoteTest(unittest.TestCase):
    def test_parse_neither(self) -> None:
        self.assertEqual(
            parse_pairwise_vote('{"choice": "neither"}', "a", "b"), "neither"
        )

    def test_blocks_when_neither(self) -> None:
        os.environ["CRE_LIBRARIAN_PAIRWISE_VOTE"] = "1"
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_PAIRWISE_VOTE", None)

        def llm(_s: str, _u: str) -> str:
            return '{"choice": "neither"}'

        self.assertTrue(
            pairwise_blocks_auto_link(
                "section",
                ["111-111", "222-222"],
                candidate_meta=[
                    {"cre_id": "111-111", "name": "A"},
                    {"cre_id": "222-222", "name": "B"},
                ],
                llm_fn=llm,
            )
        )

    def test_off_by_default(self) -> None:
        os.environ.pop("CRE_LIBRARIAN_PAIRWISE_VOTE", None)
        self.assertFalse(
            pairwise_blocks_auto_link(
                "section",
                ["111-111", "222-222"],
                candidate_meta=[],
                llm_fn=lambda _s, _u: '{"choice": "neither"}',
            )
        )


class SourceGroundingTest(unittest.TestCase):
    def test_parse_verdicts(self) -> None:
        self.assertEqual(
            parse_grounding_verdict('{"verdict": "supported"}'), "supported"
        )
        self.assertEqual(
            parse_grounding_verdict('{"verdict": "insufficient"}'), "insufficient"
        )

    def test_blocks_contradicted(self) -> None:
        os.environ["CRE_LIBRARIAN_SOURCE_GROUNDING"] = "1"
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_SOURCE_GROUNDING", None)

        def llm(_s: str, _u: str) -> str:
            return '{"verdict": "contradicted"}'

        self.assertTrue(
            grounding_blocks_auto_link(
                "section text",
                {"cre_id": "111-111", "name": "Access control"},
                llm_fn=llm,
            )
        )


class CrosswalkCageTest(unittest.TestCase):
    def test_filters_when_enabled(self) -> None:
        os.environ["CRE_LIBRARIAN_CROSSWALK_CAGE"] = "1"
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_CROSSWALK_CAGE", None)
        audit = RetrievalAudit(
            retriever="t",
            candidates=[
                CreCandidate(cre_id="111-111", score_vector=0.9),
                CreCandidate(cre_id="222-222", score_vector=0.8),
            ],
            reranked=[],
            threshold=0.8,
        )
        out = apply_crosswalk_cage(audit, ["222-222"])
        self.assertEqual([c.cre_id for c in out.candidates], ["222-222"])
        self.assertIn("crosswalk-cage", out.retriever)


class CoverageFailClosedTest(unittest.TestCase):
    def test_thin_shortlist(self) -> None:
        os.environ["CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED"] = "1"
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_COVERAGE_FAIL_CLOSED", None)
        self.assertTrue(coverage_is_thin([]))
        self.assertTrue(
            coverage_is_thin([CreCandidate(cre_id="111-111", score_vector=0.9)])
        )
        self.assertFalse(
            coverage_is_thin(
                [
                    CreCandidate(cre_id="111-111", score_vector=0.9),
                    CreCandidate(cre_id="222-222", score_vector=0.8),
                ]
            )
        )


class FailClosedBatchTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CRE_LIBRARIAN_PAIRWISE_VOTE"] = "1"
        os.environ["CRE_LIBRARIAN_SOURCE_GROUNDING"] = "1"
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_PAIRWISE_VOTE", None)
        self.addCleanup(os.environ.pop, "CRE_LIBRARIAN_SOURCE_GROUNDING", None)
        self.meta = [
            {"cre_id": "111-111", "name": "A"},
            {"cre_id": "222-222", "name": "B"},
        ]

    def test_parse_batched(self) -> None:
        choice, verdict = parse_batched_fail_closed(
            '{"choice": "111-111", "verdict": "supported"}', "111-111", "222-222"
        )
        self.assertEqual(choice, "111-111")
        self.assertEqual(verdict, "supported")

    def test_one_llm_call_when_both_enabled(self) -> None:
        calls: list[int] = []

        def llm(_s: str, _u: str) -> str:
            calls.append(1)
            return '{"choice": "111-111", "verdict": "supported"}'

        reason = evaluate_fail_closed_levers(
            "section",
            ["111-111", "222-222"],
            candidate_meta=self.meta,
            llm_fn=llm,
        )
        self.assertIsNone(reason)
        self.assertEqual(len(calls), 1)

    def test_batched_pairwise_disagree(self) -> None:
        reason = evaluate_fail_closed_levers(
            "section",
            ["111-111", "222-222"],
            candidate_meta=self.meta,
            llm_fn=lambda _s, _u: '{"choice": "neither", "verdict": "supported"}',
        )
        self.assertEqual(reason, ReasonCode.pairwise_disagree)

    def test_batched_grounding_blocks(self) -> None:
        reason = evaluate_fail_closed_levers(
            "section",
            ["111-111", "222-222"],
            candidate_meta=self.meta,
            llm_fn=lambda _s, _u: '{"choice": "111-111", "verdict": "insufficient"}',
        )
        self.assertEqual(reason, ReasonCode.source_unsupported)

    def test_single_flag_still_one_call(self) -> None:
        os.environ.pop("CRE_LIBRARIAN_SOURCE_GROUNDING", None)
        calls: list[int] = []

        def llm(_s: str, _u: str) -> str:
            calls.append(1)
            return '{"choice": "neither"}'

        reason = evaluate_fail_closed_levers(
            "section",
            ["111-111", "222-222"],
            candidate_meta=self.meta,
            llm_fn=llm,
        )
        self.assertEqual(reason, ReasonCode.pairwise_disagree)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
