import unittest
 
from application.defs.cheatsheet_defs import CheatsheetRecord
from application.utils.external_project_parsers.parsers.cheatsheet_record_adapter import (
    MalformedCheatsheetRecordError,
    section_from_cheatsheet_record,
)
 
 
class TestSectionFromCheatsheetRecord(unittest.TestCase):
    def test_valid_record_produces_expected_section(self):
        record = CheatsheetRecord(
            source_id="Secrets_Management_Cheat_Sheet",
            title="Secrets Management Cheat Sheet",
            hyperlink="https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
            summary="Storage guidance.",
            headings=["Introduction", "Architectural Patterns"],
            raw_markdown_path="cheatsheets/Secrets_Management_Cheat_Sheet.md",
            metadata={
                "parser_version": "v1",
                "fallback_used": "false",
                "committed_at": "2026-06-14T10:22:03+00:00",
            },
        )
 
        section = section_from_cheatsheet_record(record)
 
        self.assertEqual(section.chunk_id, "chk:owasp_cheatsheets:Secrets_Management_Cheat_Sheet")
        self.assertEqual(section.artifact_id, "art:owasp_cheatsheets:Secrets_Management_Cheat_Sheet")
        self.assertEqual(section.text, "Storage guidance.\nIntroduction\nArchitectural Patterns")
        self.assertEqual(section.title_hint, "Secrets Management Cheat Sheet")
        self.assertEqual(section.language, "en")
        self.assertEqual(
            str(section.source.url),
            "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
        )
        self.assertEqual(section.locator.id, "Secrets_Management_Cheat_Sheet")
        self.assertEqual(
            str(section.locator.url),
            "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
        )
 
    def test_fallback_title_and_summary_pass_through(self):
        record = CheatsheetRecord(
            source_id="Secrets_Management_Cheat_Sheet",
            title="No title found.",
            hyperlink="https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
            summary="No summary found.",
            headings=[],
            raw_markdown_path="cheatsheets/Secrets_Management_Cheat_Sheet.md",
            metadata={
                "parser_version": "v1",
                "fallback_used": "true",
                "committed_at": "2026-06-14T10:22:03+00:00",
            },
        )
 
        section = section_from_cheatsheet_record(record)
 
        self.assertEqual(section.title_hint, "No title found.")
        self.assertEqual(section.text, "No summary found.")
 
    def test_missing_committed_at_raises(self):
        record = CheatsheetRecord(
            source_id="Secrets_Management_Cheat_Sheet",
            title="Secrets Management Cheat Sheet",
            hyperlink="https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
            summary="Storage guidance.",
            headings=["Introduction"],
            raw_markdown_path="cheatsheets/Secrets_Management_Cheat_Sheet.md",
            metadata={
                "parser_version": "v1",
                "fallback_used": "false",
                "committed_at": "",
            },
        )
 
        with self.assertRaises(MalformedCheatsheetRecordError):
            section_from_cheatsheet_record(record)
 
 
if __name__ == "__main__":
    unittest.main()