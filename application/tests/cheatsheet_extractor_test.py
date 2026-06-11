import unittest
from application.utils.external_project_parsers.parsers.cheatsheet_extractor import (
    extract_cheatsheet_record,
)
from application.defs.cheatsheet_defs import SUMMARY_MAX_LENGTH

SOURCE_PATH = "cheatsheets/Secrets_Management_Cheat_Sheet.md"
EXPECTED_SOURCE_ID = "Secrets_Management_Cheat_Sheet"
EXPECTED_HYPERLINK = (
    "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"
)

NORMAL_MD = """\
# Secrets Management Cheat Sheet

## Introduction
Storage guidance.

## Architectural Patterns
Use vaults and environment isolation.
"""

MISSING_H1_MD = """\
## Introduction
No H1 present.

## Details
More content.
"""

EMPTY_MD = ""

# No ## headings — _extract_summary raises, _fallback_summary matches # via _ANY_HEADING_RE
# and extracts body until len(markdown) since there is no next heading.
BODY_UNDER_H1_MD = """\
# Single Heading Cheat Sheet

Body text directly under H1, no subheadings at all.
"""

# Leading spaces before # and ##malformed (no space) — both handled by \s* and (?!#) regex
MALFORMED_MD = """\
   # Malformed Title

##malformed

## Introduction
Some intro text.

## Valid Heading
"""


class TestNormal(unittest.TestCase):
    def setUp(self):
        self.record = extract_cheatsheet_record(NORMAL_MD, SOURCE_PATH)

    # source, source_id, hyperlink, raw_markdown_path are derived from SOURCE_PATH
    # and are independent of markdown content — verified once here for all cases
    def test_source(self):
        self.assertEqual(self.record.source, "owasp_cheatsheets")

    def test_source_id(self):
        self.assertEqual(self.record.source_id, EXPECTED_SOURCE_ID)

    def test_hyperlink(self):
        self.assertEqual(self.record.hyperlink, EXPECTED_HYPERLINK)

    def test_raw_markdown_path(self):
        self.assertEqual(self.record.raw_markdown_path, SOURCE_PATH)

    def test_title(self):
        self.assertEqual(self.record.title, "Secrets Management Cheat Sheet")

    def test_summary(self):
        self.assertEqual(self.record.summary, "Storage guidance.")

    def test_summary_bounded(self):
        # SUMMARY_MAX_LENGTH truncation happens in CheatsheetRecord.__post_init__
        # for every record — testing once here covers all cases
        self.assertLessEqual(len(self.record.summary), SUMMARY_MAX_LENGTH)

    def test_headings(self):
        self.assertIn("Introduction", self.record.headings)
        self.assertIn("Architectural Patterns", self.record.headings)

    def test_fallback_not_used(self):
        self.assertEqual(self.record.metadata["fallback_used"], "false")


class TestMissingH1(unittest.TestCase):
    def setUp(self):
        self.record = extract_cheatsheet_record(MISSING_H1_MD, SOURCE_PATH)

    def test_title_is_fallback(self):
        self.assertEqual(self.record.title, "No title found.")

    def test_summary_from_introduction(self):
        self.assertIn("no h1", self.record.summary.lower())

    def test_headings_extracted(self):
        self.assertIn("Introduction", self.record.headings)
        self.assertIn("Details", self.record.headings)

    def test_fallback_used(self):
        self.assertEqual(self.record.metadata["fallback_used"], "true")


class TestEmptyMarkdown(unittest.TestCase):
    def setUp(self):
        self.record = extract_cheatsheet_record(EMPTY_MD, SOURCE_PATH)

    def test_title_is_fallback(self):
        self.assertEqual(self.record.title, "No title found.")

    def test_summary_no_summary_found(self):
        # No headings at all — _fallback_summary returns this literal string
        self.assertEqual(self.record.summary, "No summary found.")

    def test_headings_empty(self):
        self.assertEqual(self.record.headings, [])

    def test_fallback_used(self):
        self.assertEqual(self.record.metadata["fallback_used"], "true")


class TestBodyUnderH1(unittest.TestCase):
    def setUp(self):
        self.record = extract_cheatsheet_record(BODY_UNDER_H1_MD, SOURCE_PATH)

    def test_title(self):
        self.assertEqual(self.record.title, "Single Heading Cheat Sheet")

    def test_summary_from_fallback_via_h1(self):
        # _fallback_summary matches # heading, extracts body until len(markdown)
        self.assertIn("body text", self.record.summary.lower())

    def test_headings_empty(self):
        # _HEADING_RE only matches ## — no ## present here
        self.assertEqual(self.record.headings, [])

    def test_fallback_used(self):
        self.assertEqual(self.record.metadata["fallback_used"], "true")


class TestMalformedHeadings(unittest.TestCase):
    def setUp(self):
        self.record = extract_cheatsheet_record(MALFORMED_MD, SOURCE_PATH)

    def test_malformed_h1_extracted(self):
        self.assertEqual(self.record.title, "Malformed Title")

    def test_malformed_h2_in_headings(self):
        self.assertIn("malformed", self.record.headings)

    def test_valid_headings_also_extracted(self):
        self.assertIn("Introduction", self.record.headings)
        self.assertIn("Valid Heading", self.record.headings)

    def test_summary_from_introduction(self):
        self.assertIn("intro", self.record.summary.lower())

    def test_fallback_not_used(self):
        self.assertEqual(self.record.metadata["fallback_used"], "false")


if __name__ == "__main__":
    unittest.main()
