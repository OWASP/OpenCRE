"""Tests for OWASP-agent prompt NLP normalize."""

from __future__ import annotations

import unittest

from application.utils.owasp_agent.prompt_normalize import normalize_prompt
from application.utils.owasp_agent.router import _clean_project_name


class TestNormalizePrompt(unittest.TestCase):
    def test_strips_please_and_keeps_project_tokens(self) -> None:
        out = normalize_prompt("What is the OWASP ASVS project please?")
        low = out.lower()
        self.assertIn("asvs", low)
        self.assertIn("owasp", low)
        self.assertNotIn("please", low)

    def test_strips_source_parenthetical(self) -> None:
        out = normalize_prompt("What is the OWASP Amass project? (source: OWASP.org)")
        low = out.lower()
        self.assertIn("amass", low)
        self.assertNotIn("source", low)

    def test_empty_stays_empty(self) -> None:
        self.assertEqual(normalize_prompt(""), "")
        self.assertEqual(normalize_prompt("   "), "")

    def test_casefolds_and_strips_metadata_wrapper(self) -> None:
        out = normalize_prompt(
            "(METADATA ONLY) LETHAL TRIFECTA — JUST THE THREE LEGS, NO PREAMBLE"
        )
        low = out.lower()
        self.assertIn("lethal", low)
        self.assertIn("trifecta", low)
        self.assertIn("legs", low)
        self.assertNotIn("metadata", low)
        self.assertNotIn("preamble", low)
        # Embed path must not stay ALL CAPS.
        self.assertEqual(out, out.lower())


class TestCleanProjectName(unittest.TestCase):
    def test_please_suffix(self) -> None:
        self.assertEqual(_clean_project_name("ASVS project please"), "ASVS")

    def test_source_suffix(self) -> None:
        self.assertEqual(
            _clean_project_name("Amass project? (source: OWASP.org)"),
            "Amass",
        )


if __name__ == "__main__":
    unittest.main()
