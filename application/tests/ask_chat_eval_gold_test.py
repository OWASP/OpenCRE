"""#1078: chat eval gold set shape and hermetic scorer."""

from __future__ import annotations

import unittest
from pathlib import Path

from application.utils.ask_eval.gold import (
    ABSTAIN_PREFIX,
    load_gold,
    normalize_completion,
    score_case,
    summarize,
    to_phase6_cases,
)
from application.utils.rag_parity.phase6_eval import neighbourhood_hit_at_k

GOLD = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "ask_regressions"
    / "chat_eval_gold.jsonl"
)


def _row(rows, rid):
    return next(r for r in rows if r.id == rid)


def _completion(answer, rows, accurate=True, cites=()):
    return {
        "response": answer,
        "table": rows,
        "accurate": accurate,
        "owasp_agent": {"citations": list(cites)},
    }


SAMM_ROW = {
    "name": "SAMM",
    "section": "Threat Assessment",
    "hyperlink": "https://owaspsamm.org/model/design/threat-assessment/",
}
CS_ROW = {
    "name": "Cheat_sheets",
    "section": "Threat Modeling Cheat Sheet",
    "hyperlink": "https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html",
}
CRE_ROW = {"doctype": "CRE", "id": "068-102", "name": "Threat modeling"}


class GoldSetShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_gold(GOLD)

    def test_size_in_issue_range(self) -> None:
        self.assertGreaterEqual(len(self.rows), 15)
        self.assertLessEqual(len(self.rows), 30)

    def test_ids_unique_and_expect_known(self) -> None:
        ids = [r.id for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.rows:
            self.assertIn(r.expect, ("answer", "abstain"), r.id)
            self.assertTrue(r.question.strip(), r.id)

    def test_seeds_named_in_issue_are_present(self) -> None:
        ids = {r.id for r in self.rows}
        self.assertTrue({"tm_people", "tm_people_samm", "pw_storage"} <= ids)
        self.assertTrue(any(r.family == "ai_security" for r in self.rows))
        self.assertTrue(any(r.expect == "abstain" for r in self.rows))

    def test_samm_row_requires_samm_cite(self) -> None:
        samm = _row(self.rows, "tm_people_samm")
        self.assertIn("samm", samm.required_cite_groups)

    def test_answer_rows_name_cre_ids(self) -> None:
        for r in self.rows:
            if r.expect == "answer":
                self.assertTrue(r.expected_cre_ids, r.id)
                for cid in r.expected_cre_ids:
                    self.assertRegex(cid, r"^\d{3}-\d{3}$", r.id)


class ScorerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_gold(GOLD)

    def test_samm_question_fails_without_samm_cite(self) -> None:
        # Rob's #962 case: right topic, but the answer came from the cheat sheet only.
        resp = normalize_completion(
            _completion("Pick people who know the system [1].", [CS_ROW, CRE_ROW])
        )
        s = score_case(_row(self.rows, "tm_people_samm"), resp)
        self.assertTrue(s.cre_hit)
        self.assertEqual(list(s.missing_groups), ["samm"])
        self.assertFalse(s.passed)

    def test_samm_question_passes_with_samm_cite(self) -> None:
        resp = normalize_completion(
            _completion(
                "SAMM's threat assessment practice [1], see also [2].",
                [SAMM_ROW, CRE_ROW],
            )
        )
        s = score_case(_row(self.rows, "tm_people_samm"), resp)
        self.assertTrue(s.passed, s)

    def test_marker_past_returned_passages_is_flagged(self) -> None:
        resp = normalize_completion(_completion("Do this [1] and that [3].", [CRE_ROW]))
        s = score_case(_row(self.rows, "tm_people"), resp)
        self.assertEqual(list(s.bad_markers), [3])
        self.assertFalse(s.passed)

    def test_cre_id_found_in_citation_url(self) -> None:
        resp = normalize_completion(
            _completion(
                "Escape output [1].", [], cites=["https://opencre.org/cre/760-765"]
            )
        )
        self.assertIn("760-765", resp.cre_ids)

    def test_abstain_rows(self) -> None:
        row = _row(self.rows, "refuse_off_topic")
        refused = normalize_completion(
            _completion(ABSTAIN_PREFIX + ", so I won't guess.", [], accurate=False)
        )
        essay = normalize_completion(_completion("Mix flour and bananas.", [CS_ROW]))
        self.assertTrue(score_case(row, refused).passed)
        self.assertFalse(score_case(row, essay).passed)

    def test_answer_row_that_abstains_is_a_false_abstain(self) -> None:
        resp = normalize_completion(_completion(ABSTAIN_PREFIX, [], accurate=False))
        s = score_case(_row(self.rows, "sqli"), resp)
        self.assertFalse(s.abstain_ok)
        self.assertFalse(s.passed)

    def test_must_contain_any(self) -> None:
        row = _row(self.rows, "sqli")
        ok = normalize_completion(
            _completion("Use parameterized queries [1].", [{"id": "732-873"}])
        )
        vague = normalize_completion(
            _completion("Be careful with input [1].", [{"id": "732-873"}])
        )
        self.assertTrue(score_case(row, ok).contains_ok)
        self.assertFalse(score_case(row, vague).contains_ok)

    def test_summary_counts_only_rows_with_groups(self) -> None:
        tm = _row(self.rows, "tm_people")
        samm = _row(self.rows, "tm_people_samm")
        resp = normalize_completion(_completion("[1]", [CS_ROW, CRE_ROW]))
        out = summarize([score_case(tm, resp), score_case(samm, resp)])
        self.assertEqual(out["cite_group_recall"], 0.0)
        self.assertEqual(out["cre_recall"], 1.0)
        self.assertEqual(out["failed"], ["tm_people_samm"])

    def test_bridges_to_phase6_hit_at_k(self) -> None:
        cases = to_phase6_cases(self.rows)
        self.assertEqual(len(cases), sum(1 for r in self.rows if r.expect == "answer"))
        by_q = {r.question: list(r.expected_cre_ids) for r in self.rows}
        self.assertEqual(neighbourhood_hit_at_k(cases, lambda q: by_q[q]), 1.0)
        self.assertEqual(neighbourhood_hit_at_k(cases, lambda q: []), 0.0)


if __name__ == "__main__":
    unittest.main()
