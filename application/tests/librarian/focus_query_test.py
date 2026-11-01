"""Tests for C.2 focus-query (metadata-only) helper."""

from __future__ import annotations

import unittest

from application.utils.librarian.focus_query import (
    body_query_text,
    focus_query_text,
    name_pack_query_text,
    split_retrieval_query,
)


class FocusQueryTest(unittest.TestCase):
    def test_keeps_metadata_drops_body(self) -> None:
        text = (
            "Standard: owasp_top10_2025\n"
            "Version: 2025\n"
            "Source: A01.txt\n"
            "Section-ID: A01\n"
            "Section: Broken Access Control\n"
            "\n"
            "Long narrative about access control that should not enter the CE query.\n"
        )
        focus = focus_query_text(text)
        self.assertIn("Standard: owasp_top10_2025", focus)
        self.assertIn("Version: 2025", focus)
        self.assertIn("Section-ID: A01", focus)
        self.assertNotIn("Long narrative", focus)

    def test_empty_without_metadata(self) -> None:
        self.assertEqual(focus_query_text("just a paragraph\n"), "")


class NamePackQueryTest(unittest.TestCase):
    def test_omits_standard_and_version(self) -> None:
        text = (
            "Standard: OWASP Kubernetes Top 10 2022\n"
            "Version: 2022\n"
            "Source: K06\n"
            "Section: Broken Authentication Mechanisms\n"
            "Section-ID: K06\n"
            "\n"
            "Narrative about authn.\n"
        )
        pack = name_pack_query_text(text)
        self.assertNotIn("Standard:", pack)
        self.assertNotIn("Version:", pack)
        self.assertIn("Section-ID: K06", pack)
        self.assertIn("Broken Authentication Mechanisms", pack)
        self.assertNotIn("Narrative", pack)


class SplitRetrievalQueryTest(unittest.TestCase):
    def test_header_is_titles_body_is_narrative(self) -> None:
        text = (
            "Standard: OWASP Top 10 2025\n"
            "Version: 2025\n"
            "Source: A01\n"
            "Section: Broken Access Control\n"
            "Section-ID: A01\n"
            "\n"
            "Long narrative about IDOR and privilege escalation.\n"
        )
        header, body = split_retrieval_query(text)
        self.assertIn("Broken Access Control", header)
        self.assertIn("Section-ID: A01", header)
        self.assertNotIn("Standard:", header)
        self.assertNotIn("Version:", header)
        self.assertNotIn("IDOR", header)
        self.assertIn("IDOR", body)
        self.assertNotIn("Section: Broken Access Control", body)
        self.assertEqual(body_query_text(text), body)

    def test_no_header_skips_short_path(self) -> None:
        header, body = split_retrieval_query("just a paragraph about auth\n")
        self.assertEqual(header, "")
        self.assertIn("just a paragraph", body)


if __name__ == "__main__":
    unittest.main()
