"""Tests for C.2 focus-query (metadata-only) helper."""

from __future__ import annotations

import unittest

from application.utils.librarian.focus_query import focus_query_text


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


if __name__ == "__main__":
    unittest.main()
