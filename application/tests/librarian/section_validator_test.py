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
    """A `knowledge_queue` row in Module B's merged v0.2 shape (#989)."""
    row = {
        "id": "4a8c1b2e-1d2f-4e3a-9b4c-5d6e7f8a9b0c",
        "content_hash": "9f2a1c7d3e5b8a04c6d1e2f3a4b5c6d7",
        "chunk_id": "chk:art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md:0",
        "artifact_id": "art:OWASP/ASVS:4.0/en/0x11-V2-Authentication.md",
        "pipeline_run_id": "run-001",
        "schema_version": "0.2.0",
        "source_type": "github",
        "source_repo": "OWASP/ASVS",
        "source_commit_sha": "abc123def456789012345678901234567890abcd",
        "source_committed_at": "2026-05-24T18:02:11Z",
        "feed_url": None,
        "post_guid": None,
        "locator_kind": "repo_path",
        "locator_path": "4.0/en/0x11-V2-Authentication.md",
        "span_index": 0,
        "span_total": 3,
        "span_heading_path": '["V2 Authentication","V2.1 Password Security"]',
        "text": "Verify that user-set passwords are at least 12 characters long.",
        "confidence": 0.93,
        "llm_label": "KNOWLEDGE",
        "llm_reasoning": "clear security requirement",
        "created_at": "2026-05-25T02:25:00Z",
        "consumed_at": None,
    }
    row.update(overrides)
    return row


def valid_rss_row(**overrides) -> dict:
    """The other shape B writes: a feed post, with no repo or commit at all."""
    row = valid_queue_row(
        id="7dbf4e51-4a5c-4b6d-ce7f-8a9b0c1d2e3f",
        chunk_id="chk:art:owasp-blog:session-fixation:0",
        artifact_id="art:owasp-blog:session-fixation",
        source_type="rss",
        source_repo=None,
        source_commit_sha=None,
        source_committed_at=None,
        feed_url="https://owasp.org/blog/feed.xml",
        post_guid="https://owasp.org/blog/2026/05/20/session-fixation",
        locator_kind="feed_item",
        locator_path="https://owasp.org/blog/2026/05/20/session-fixation.html",
        span_heading_path='["Preventing session fixation"]',
        text="Regenerate the session id after authentication.",
    )
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
    def test_identity_is_read_from_the_row_not_synthesized(self) -> None:
        """The W8 contract fix: A's ids pass through C untouched.

        Through W7 these were built out of repo/path/sha, which produced ids
        matching nothing upstream. Pinning both to the row's own values is what
        lets a link join back to the artifact Module A harvested.
        """
        row = valid_queue_row()
        section = section_from_queue_row(row)
        self.assertIsInstance(section, Section)
        self.assertEqual(section.chunk_id, row["chunk_id"])
        self.assertEqual(section.artifact_id, row["artifact_id"])

    def test_github_row_maps_source_and_locator(self) -> None:
        section = section_from_queue_row(valid_queue_row())
        self.assertEqual(section.source.type.value, "github")
        self.assertEqual(section.source.repo, "OWASP/ASVS")
        # A's real commit time, not B's classification time.
        self.assertEqual(
            section.source.committed_at,
            datetime(2026, 5, 24, 18, 2, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(section.locator.path, "4.0/en/0x11-V2-Authentication.md")
        self.assertEqual(section.language, "en")

    def test_committed_at_falls_back_to_created_at(self) -> None:
        """`source_committed_at` is github-only and nullable; created_at is the
        best provenance a row without one carries."""
        section = section_from_queue_row(valid_queue_row(source_committed_at=None))
        self.assertEqual(
            section.source.committed_at,
            datetime(2026, 5, 25, 2, 25, tzinfo=timezone.utc),
        )

    def test_rss_row_is_accepted_with_no_repo_or_sha(self) -> None:
        """The whole RSS path was unrepresentable before W8: C required a repo
        and a commit sha that B leaves NULL on every feed row."""
        section = section_from_queue_row(valid_rss_row())
        self.assertEqual(section.source.type.value, "rss")
        self.assertIsNone(section.source.repo)
        self.assertIsNone(section.source.commit_sha)
        self.assertEqual(section.locator.kind.value, "feed_item")
        # The guid is the stable identity for a feed item; the path is the URL.
        self.assertEqual(
            section.locator.id, "https://owasp.org/blog/2026/05/20/session-fixation"
        )

    def test_title_hint_comes_from_the_heading_path(self) -> None:
        section = section_from_queue_row(valid_queue_row())
        self.assertEqual(section.title_hint, "V2.1 Password Security")

    def test_unparseable_heading_path_degrades_to_no_title(self) -> None:
        """A cosmetic field must not cost an otherwise linkable row."""
        section = section_from_queue_row(valid_queue_row(span_heading_path="{oops"))
        self.assertIsNone(section.title_hint)

    def test_volatile_metadata_not_carried_into_section(self) -> None:
        section = section_from_queue_row(
            valid_queue_row(llm_reasoning="audit-only rationale")
        )
        self.assertFalse(hasattr(section, "llm_reasoning"))
        self.assertFalse(hasattr(section, "confidence"))

    def test_uncertain_rows_are_accepted(self) -> None:
        """Module B is recall-first: it drops NOISE and forwards KNOWLEDGE and
        UNCERTAIN. An UNCERTAIN chunk is one B was unsure about classifying, not
        one it judged worthless, so the boundary lets it through — rejecting it
        here meant nothing ever retrieved candidates for it.

        The row still records which label it came from, so a consumer can weigh
        a decision made on an uncertain chunk differently.
        """
        section = section_from_queue_row(valid_queue_row(llm_label="UNCERTAIN"))

        self.assertTrue(section.text)

    def test_rejection_table(self) -> None:
        cases = [
            ("empty text", valid_queue_row(text=""), EmptyTextError),
            ("whitespace text", valid_queue_row(text="  \n\t "), EmptyTextError),
            ("noise label", valid_queue_row(llm_label="NOISE"), NotKnowledgeError),
            (
                "unknown label",
                valid_queue_row(llm_label="SOMETHING_ELSE"),
                NotKnowledgeError,
            ),
            (
                "missing field",
                {k: v for k, v in valid_queue_row().items() if k != "chunk_id"},
                MalformedKnowledgeItemError,
            ),
            (
                "wrong type",
                valid_queue_row(confidence="very sure"),
                MalformedKnowledgeItemError,
            ),
            ("not a mapping", "just a string", MalformedKnowledgeItemError),
            # source_type and the populated source columns must agree: B nulls
            # repo/sha for rss, so a github row without them is a contract
            # breach, and it has to surface as one typed boundary rejection
            # rather than a raw error out of the RFC SourceRef.
            (
                "github row with no repo",
                valid_queue_row(source_repo=None),
                MalformedKnowledgeItemError,
            ),
            (
                "github row with no sha",
                valid_queue_row(source_commit_sha=None),
                MalformedKnowledgeItemError,
            ),
            (
                "rss row with no feed url",
                valid_rss_row(feed_url=None),
                MalformedKnowledgeItemError,
            ),
            # Module A's contract allows a 4-character sha; the RFC SourceRef
            # requires 7. That row is malformed for C, and must not escape as a
            # raw Pydantic error from outside the validation call.
            (
                "sha shorter than the RFC allows",
                valid_queue_row(source_commit_sha="abcd"),
                MalformedKnowledgeItemError,
            ),
            (
                "feed item whose locator is not a url",
                valid_rss_row(locator_path="not-a-url"),
                MalformedKnowledgeItemError,
            ),
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
