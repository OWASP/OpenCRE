"""Offline checks for the chapter-start regression fixture and its answer grader."""

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

from application.utils.ask_eval.multicite import missing_cite_groups

FIXTURE = (
    Path(__file__).parent / "fixtures" / "ask_regressions" / "chapter_start_pune.jsonl"
)


def grade(row: Dict[str, Any], answer: str, cites: List[str]) -> List[str]:
    """Reasons ``answer`` fails the row (empty list = pass)."""
    low = answer.lower()
    fails = [
        f"missing cite group: {g}"
        for g in missing_cite_groups(cites, row["required_cite_groups"])
    ]
    any_of = row.get("must_contain_any") or []
    if any_of and not any(s.lower() in low for s in any_of):
        fails.append(f"none of {any_of} in answer")
    fails += [
        f"forbidden: {s}" for s in row.get("must_not_contain") or [] if s.lower() in low
    ]
    return fails


class ChapterStartFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            json.loads(x) for x in FIXTURE.read_text().splitlines() if x.strip()
        ]

    def test_rows_are_well_formed(self) -> None:
        self.assertGreaterEqual(len(self.rows), 2)
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.rows:
            for key in (
                "question",
                "reference",
                "required_cite_groups",
                "must_not_contain",
            ):
                self.assertIn(key, r)

    def test_grader_passes_the_good_answer_and_fails_the_original_bug(self) -> None:
        pune = next(r for r in self.rows if r["id"] == "pune_start_chapter_exists")
        good = "An OWASP Pune chapter already exists; a new chapter within 80 km may be denied."
        cites = [
            "https://github.com/OWASP/www-policy/blob/HEAD/operational/chapters.md",
            "https://github.com/OWASP/www-chapter-pune/blob/HEAD/index.md",
        ]
        self.assertEqual(grade(pune, good, cites), [])
        bad = "There is no chapter in Pune. Submit a Chapter Request Form."
        self.assertTrue(grade(pune, bad, ["https://x/2017-handbook"]))


if __name__ == "__main__":
    unittest.main()
