"""Regression: AI Exchange ask answers should cite AIX *and* www-board.

These questions already live in the private ask ablate set. This fixture locks
the multi-cite expectation (board is desired, not contamination).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from application.utils.ask_eval.multicite import (
    assert_required_cite_groups,
    group_covered,
    missing_cite_groups,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "ask_regressions"
    / "ai_board_multicite.jsonl"
)


def _load_fixture() -> list[dict]:
    rows: list[dict] = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class TestAskAiBoardMulticite(unittest.TestCase):
    def test_fixture_has_core_aix_questions(self) -> None:
        rows = _load_fixture()
        self.assertGreaterEqual(len(rows), 3)
        ids = {r["id"] for r in rows}
        self.assertIn("aix_hero_templates_multicite", ids)
        self.assertIn("aix_site_render_search_multicite", ids)
        for row in rows:
            self.assertIn("aix", row["required_cite_groups"])
            self.assertIn("board", row["required_cite_groups"])
            self.assertTrue(row["question"])
            self.assertEqual(
                row["repo"], "OWASP/www-project-ai-security-and-privacy-guide"
            )

    def test_group_covered_matches_needles(self) -> None:
        cites = [
            "https://github.com/OWASP/www-project-ai-security-and-privacy-guide/blob/HEAD/content/ai_exchange/HERO_SECTIONS_GUIDE.md",
            "https://github.com/OWASP/www-board/blob/HEAD/board_history_by_member.md",
        ]
        self.assertTrue(group_covered(cites, ["ai_exchange", "HERO_SECTIONS"]))
        self.assertTrue(group_covered(cites, ["www-board"]))
        self.assertFalse(group_covered(cites, ["pagefind"]))

    def test_missing_groups_when_only_aix(self) -> None:
        cites = [
            "https://github.com/OWASP/www-project-ai-security-and-privacy-guide/blob/HEAD/content/ai_exchange/HERO_SECTIONS_GUIDE.md",
        ]
        groups = {
            "aix": ["ai_exchange"],
            "board": ["www-board", "board_history"],
        }
        self.assertEqual(missing_cite_groups(cites, groups), ["board"])

    def test_missing_groups_when_only_board(self) -> None:
        cites = ["https://github.com/OWASP/www-board/blob/HEAD/README.md"]
        groups = {
            "aix": ["ai_exchange", "owaspai.org"],
            "board": ["www-board"],
        }
        self.assertEqual(missing_cite_groups(cites, groups), ["aix"])

    def test_assert_passes_when_both_families_present(self) -> None:
        row = next(
            r for r in _load_fixture() if r["id"] == "aix_hero_templates_multicite"
        )
        cites = [
            "https://github.com/OWASP/www-project-ai-security-and-privacy-guide/blob/HEAD/content/ai_exchange/HERO_SECTIONS_GUIDE.md",
            "https://github.com/OWASP/www-board/blob/HEAD/README.md",
        ]
        assert_required_cite_groups(cites, row["required_cite_groups"])

    def test_assert_fails_without_board(self) -> None:
        row = next(
            r for r in _load_fixture() if r["id"] == "aix_hero_templates_multicite"
        )
        cites = [
            "https://github.com/OWASP/www-project-ai-security-and-privacy-guide/blob/HEAD/content/ai_exchange/HERO_SECTIONS_GUIDE.md",
        ]
        with self.assertRaises(AssertionError) as ctx:
            assert_required_cite_groups(cites, row["required_cite_groups"])
        self.assertIn("board", str(ctx.exception))

    def test_hero_question_matches_ablate_wording(self) -> None:
        row = next(
            r for r in _load_fixture() if r["id"] == "aix_hero_templates_multicite"
        )
        self.assertIn("HERO_SECTIONS_GUIDE.md", row["question"])
        self.assertIn("filenames", row["question"])


if __name__ == "__main__":
    unittest.main()
