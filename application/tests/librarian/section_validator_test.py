"""Tests for the C.0 input boundary (section_validator).

Table-driven over every rejection class plus the happy paths for both
upstream shapes (knowledge_queue row and RFC KnowledgeItem envelope).
Asserts the boundary never leaks a raw Pydantic ValidationError.
"""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from application.utils.librarian.section_validator import (
    EmptyTextError,
    MalformedKnowledgeItemError,
    NotKnowledgeError,
    Section,
    SectionValidationError,
    UnsupportedLanguageError,
    section_from_knowledge_item,
    section_from_queue_row,
)


def valid_queue_row(**overrides) -> dict:
    row = {
        "id": "4a8c1b2e-1d2f-4e3a-9b4c-5d6e7f8a9b0c",
        "source_repo": "OWASP/ASVS",
        "source_path": "4.0/en/0x11-V2-Authentication.md",
        "source_commit_sha": "abc123def456789012345678901234567890abcd",
        "text": "Verify that user-set passwords are at least 12 characters long.",
        "confidence": 0.93,
        "llm_label": "KNOWLEDGE",
        "llm_reasoning": "clear security requirement",
        "created_at": "2026-05-25T02:25:00Z",
        "consumed_at": None,
    }
    row.update(overrides)
    return row


def valid_knowledge_item(**overrides) -> dict:
    item = {
        "schema_version": "0.2.0",
        "chunk_id": "chk:art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md:0",
        "artifact_id": "art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md",
        "event_id": "evt-001",
        "pipeline_run_id": "20260601T020000Z",
        "filtered_at": "2026-06-01T02:10:00Z",
        "status": "accepted",
        "source": {
            "type": "github",
            "repo": "OWASP/ASVS",
            "commit_sha": "abc123def456789012345678901234567890abcd",
            "committed_at": "2026-06-01T01:00:00Z",
        },
        "locator": {
            "kind": "repo_path",
            "id": "4.0/en/0x11-V2-Authentication.md",
            "path": "4.0/en/0x11-V2-Authentication.md",
        },
        "content": {
            "text": "Verify that user-set passwords are at least 12 characters long.",
            "title_hint": "Password length",
            "language": "en",
        },
        "filter": {
            "stages": [{"name": "llm_relevance", "passed": True}],
            "is_security_knowledge": True,
            "confidence": 0.93,
        },
    }
    item.update(overrides)
    return item


class QueueRowBoundaryTest(unittest.TestCase):
    def test_valid_row_builds_section_with_synthesized_identity(self) -> None:
        section = section_from_queue_row(valid_queue_row())
        self.assertIsInstance(section, Section)
        self.assertEqual(
            section.chunk_id,
            "chk:OWASP/ASVS@abc123def456789012345678901234567890abcd:"
            "4.0/en/0x11-V2-Authentication.md",
        )
        self.assertEqual(
            section.artifact_id, "art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md"
        )
        self.assertEqual(section.source.repo, "OWASP/ASVS")
        self.assertEqual(
            section.source.committed_at,
            datetime(2026, 5, 25, 2, 25, tzinfo=timezone.utc),
        )
        self.assertEqual(section.locator.path, "4.0/en/0x11-V2-Authentication.md")
        self.assertEqual(section.language, "en")

    def test_volatile_metadata_not_carried_into_section(self) -> None:
        section = section_from_queue_row(
            valid_queue_row(llm_reasoning="audit-only rationale")
        )
        self.assertFalse(hasattr(section, "llm_reasoning"))
        self.assertFalse(hasattr(section, "confidence"))

    def test_rejection_table(self) -> None:
        cases = [
            ("empty text", valid_queue_row(text=""), EmptyTextError),
            ("whitespace text", valid_queue_row(text="  \n\t "), EmptyTextError),
            ("noise label", valid_queue_row(llm_label="NOISE"), NotKnowledgeError),
            (
                "uncertain label",
                valid_queue_row(llm_label="UNCERTAIN"),
                NotKnowledgeError,
            ),
            (
                "missing field",
                {k: v for k, v in valid_queue_row().items() if k != "source_repo"},
                MalformedKnowledgeItemError,
            ),
            (
                "wrong type",
                valid_queue_row(confidence="very sure"),
                MalformedKnowledgeItemError,
            ),
            ("not a mapping", "just a string", MalformedKnowledgeItemError),
        ]
        for name, row, expected_error in cases:
            with self.subTest(name):
                with self.assertRaises(expected_error):
                    section_from_queue_row(row)

    def test_never_leaks_raw_pydantic_error(self) -> None:
        try:
            section_from_queue_row({"id": "x"})
        except SectionValidationError as exc:
            self.assertNotIsInstance(exc, ValidationError)
            self.assertIsInstance(exc.__cause__, ValidationError)
        else:
            self.fail("expected SectionValidationError")


class KnowledgeItemBoundaryTest(unittest.TestCase):
    def test_valid_item_builds_section(self) -> None:
        section = section_from_knowledge_item(valid_knowledge_item())
        self.assertEqual(
            section.chunk_id, "chk:art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md:0"
        )
        self.assertEqual(section.title_hint, "Password length")
        self.assertEqual(section.language, "en")

    def test_missing_language_defaults_to_english(self) -> None:
        item = valid_knowledge_item()
        del item["content"]["language"]
        self.assertEqual(section_from_knowledge_item(item).language, "en")

    def test_regional_english_variant_is_accepted(self) -> None:
        item = valid_knowledge_item()
        item["content"]["language"] = "en-GB"
        self.assertEqual(section_from_knowledge_item(item).language, "en-GB")

    def test_rejection_table(self) -> None:
        rejected = valid_knowledge_item(
            status="rejected",
            content=None,
            rejection={"reason_code": "NOT_SECURITY"},
        )
        unsupported_lang = valid_knowledge_item()
        unsupported_lang["content"]["language"] = "fr"
        whitespace_text = valid_knowledge_item()
        whitespace_text["content"]["text"] = "   "
        malformed = valid_knowledge_item()
        del malformed["source"]

        cases = [
            ("status rejected", rejected, NotKnowledgeError),
            ("unsupported language", unsupported_lang, UnsupportedLanguageError),
            ("whitespace text", whitespace_text, EmptyTextError),
            ("missing source", malformed, MalformedKnowledgeItemError),
        ]
        for name, item, expected_error in cases:
            with self.subTest(name):
                with self.assertRaises(expected_error):
                    section_from_knowledge_item(item)


if __name__ == "__main__":
    unittest.main()
