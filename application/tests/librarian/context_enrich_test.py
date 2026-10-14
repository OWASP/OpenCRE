"""Tests for Standard/Section context enrichment (default-off flag)."""

from __future__ import annotations

import unittest

from application.utils.librarian.context_enrich import enrich_query_context


class ContextEnrichTest(unittest.TestCase):
    def test_skips_when_headers_already_present(self) -> None:
        text = (
            "Standard: OWASP Top 10\n"
            "Section: Broken Access Control\n"
            "\n"
            "Narrative body.\n"
        )
        self.assertEqual(enrich_query_context(text, standard="X", section="Y"), text)

    def test_prepends_missing_standard_and_section(self) -> None:
        text = "Short requirement about prompt injection."
        out = enrich_query_context(
            text,
            standard="OWASP LLM Top 10",
            section="LLM01 Prompt Injection",
        )
        self.assertIn("Standard: OWASP LLM Top 10", out)
        self.assertIn("Section: LLM01 Prompt Injection", out)
        self.assertIn("Short requirement about prompt injection.", out)
        self.assertTrue(out.startswith("Standard:"))

    def test_uses_title_hint_for_section_only(self) -> None:
        text = "Standard: Already here\n\nBody only.\n"
        out = enrich_query_context(text, title_hint="API5 Broken Function Level Auth")
        self.assertIn("Standard: Already here", out)
        self.assertIn("Section: API5 Broken Function Level Auth", out)
        # Do not double Standard.
        self.assertEqual(out.count("Standard:"), 1)

    def test_source_fallback_for_standard(self) -> None:
        text = "Source: LLM01.md\n\nJust a title-ish body.\n"
        out = enrich_query_context(text, section="Prompt Injection")
        self.assertIn("Standard: LLM01.md", out)
        self.assertIn("Section: Prompt Injection", out)


if __name__ == "__main__":
    unittest.main()
