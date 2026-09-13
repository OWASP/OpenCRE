"""Tests for CRE coverage-gap id/name suggestions."""

import unittest

from application.utils.librarian.cre_gap_suggester import (
    propose_cre_external_id,
    propose_cre_name,
    suggest_gap_cre,
    too_close,
)


class TooCloseTest(unittest.TestCase):
    def test_identical_is_close(self) -> None:
        self.assertTrue(too_close("177-260", "177-260"))

    def test_one_digit_diff_is_close(self) -> None:
        self.assertTrue(too_close("177-260", "177-261"))

    def test_two_digit_diff_is_ok(self) -> None:
        self.assertFalse(too_close("177-260", "188-360"))


class ProposeIdTest(unittest.TestCase):
    def test_avoids_existing_and_neighbors(self) -> None:
        existing = {"100-100", "100-101", "200-200"}
        text = "Section-ID: A07\nSection: Authentication Failures\n"
        proposed = propose_cre_external_id(text, existing)
        self.assertRegex(proposed, r"^\d{3}-\d{3}$")
        self.assertNotIn(proposed, existing)
        for e in existing:
            self.assertFalse(too_close(proposed, e), msg=f"{proposed} vs {e}")

    def test_stable_for_same_text(self) -> None:
        existing = {"111-111"}
        text = "Section: Prompt Injection\nSection-ID: LLM01\n"
        a = propose_cre_external_id(text, existing)
        b = propose_cre_external_id(text, existing)
        self.assertEqual(a, b)


class ProposeNameTest(unittest.TestCase):
    def test_uses_section_title(self) -> None:
        name = propose_cre_name(
            "Standard: owasp_top10_2025\nSection: Authentication Failures\n"
        )
        self.assertIn("Authentication Failures", name)


class SuggestGapTest(unittest.TestCase):
    def test_full_proposal(self) -> None:
        gap = suggest_gap_cre(
            "Section-ID: A07\nSection: Authentication Failures\n",
            {"616-305", "177-260"},
        )
        self.assertRegex(gap.external_id, r"^\d{3}-\d{3}$")
        self.assertIn("Authentication", gap.name)
        self.assertIn("gap", gap.rationale.lower())


if __name__ == "__main__":
    unittest.main()
