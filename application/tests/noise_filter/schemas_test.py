"""Tests for application.utils.noise_filter.schemas and hashing.

Uses unittest (not pytest) to match the project-wide discovery pattern in
cre.py (`unittest.TestLoader().discover("application/tests", pattern="*_test.py")`).

Test groups:
    1. ModuleAMockTests        -- round-trip Module A's mock JSONL through Pydantic
    2. ChangeRecordTests       -- positive / negative / forward-compat
    3. SourceUnionTests        -- discriminated union accepts both github and rss
    4. ContentHashTests        -- compute_content_hash determinism + normalization
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from application.utils.noise_filter import hashing
from application.utils.noise_filter.schemas import (
    ChangeRecord,
    GithubSource,
    Locator,
    RssSource,
    Span,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "module_a_mock.jsonl"


# --- 1. Round-trip Module A's mock ---------------------------------------


class ModuleAMockTests(unittest.TestCase):
    """Every line of Module A's mock JSONL parses through ChangeRecord."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_lines = FIXTURE_PATH.read_text().splitlines()
        cls.records = [json.loads(line) for line in cls.raw_lines]

    def test_fixture_has_records(self) -> None:
        self.assertEqual(len(self.records), 20)

    def test_each_record_parses(self) -> None:
        for i, raw in enumerate(self.records):
            with self.subTest(index=i):
                rec = ChangeRecord.model_validate(raw)
                self.assertEqual(rec.text, raw["text"])
                self.assertEqual(rec.source.type, raw["source"]["type"])

    def test_roundtrip_dump_then_parse(self) -> None:
        """dump(parse(x)) re-parses cleanly -- schema is internally consistent."""
        for i, raw in enumerate(self.records):
            with self.subTest(index=i):
                rec = ChangeRecord.model_validate(raw)
                dumped = rec.model_dump()
                ChangeRecord.model_validate(dumped)  # must not raise


# --- 2. ChangeRecord positive / negative ---------------------------------

VALID_GITHUB_RECORD = {
    "schema_version": "0.2.0",
    "chunk_id": "chk:test:0",
    "artifact_id": "art:test",
    "pipeline_run_id": "20260529T000000Z",
    "text": "## Mitigation\n\nUse parameterized queries.",
    "span": {
        "index": 0,
        "total": 1,
        "heading_path": ["SQL Injection", "Mitigation"],
        "start_char_idx": 0,
        "end_char_idx": 42,
        "start_line": 1,
        "end_line": 3,
    },
    "source": {
        "type": "github",
        "repo": "OWASP/wstg",
        "commit_sha": "abc123def456abc123def456abc123def456abc1",
        "committed_at": "2026-05-29T12:00:00Z",
    },
    "locator": {
        "kind": "repo_path",
        "id": "doc/sql-injection.md",
        "path": "doc/sql-injection.md",
    },
}

VALID_RSS_RECORD = {
    "schema_version": "0.2.0",
    "chunk_id": "chk:rss:0",
    "artifact_id": "art:owasp_blog:jwt-kid",
    "pipeline_run_id": "20260529T000000Z",
    "text": "Validate kid against an allow-list.",
    "span": {"index": 0, "total": 1, "heading_path": ["Mitigation"]},
    "source": {
        "type": "rss",
        "feed_url": "https://owasp.org/blog/feed.xml",
        "post_guid": "https://owasp.org/blog/2026/jwt-kid",
        "post_published_at": "2026-05-29T09:00:00Z",
    },
    "locator": {
        "kind": "feed_post",
        "id": "https://owasp.org/blog/2026/jwt-kid",
        "path": "/blog/2026/jwt-kid",
    },
}


class ChangeRecordTests(unittest.TestCase):

    def test_valid_github_record_parses(self) -> None:
        rec = ChangeRecord.model_validate(VALID_GITHUB_RECORD)
        self.assertEqual(rec.source.type, "github")
        self.assertEqual(rec.source.repo, "OWASP/wstg")
        self.assertEqual(rec.span.heading_path, ["SQL Injection", "Mitigation"])

    def test_valid_rss_record_parses(self) -> None:
        rec = ChangeRecord.model_validate(VALID_RSS_RECORD)
        self.assertEqual(rec.source.type, "rss")
        self.assertEqual(rec.source.feed_url, "https://owasp.org/blog/feed.xml")

    def test_missing_required_field_raises(self) -> None:
        bad = {k: v for k, v in VALID_GITHUB_RECORD.items() if k != "text"}
        with self.assertRaises(ValidationError):
            ChangeRecord.model_validate(bad)

    def test_missing_nested_source_field_raises(self) -> None:
        bad = json.loads(json.dumps(VALID_GITHUB_RECORD))  # deep copy
        del bad["source"]["commit_sha"]
        with self.assertRaises(ValidationError):
            ChangeRecord.model_validate(bad)

    def test_unknown_source_type_raises(self) -> None:
        bad = json.loads(json.dumps(VALID_GITHUB_RECORD))
        bad["source"]["type"] = "unknown_source"
        with self.assertRaises(ValidationError):
            ChangeRecord.model_validate(bad)

    def test_invalid_repo_format_raises(self) -> None:
        bad = json.loads(json.dumps(VALID_GITHUB_RECORD))
        bad["source"]["repo"] = "no-slash"
        with self.assertRaises(ValidationError):
            ChangeRecord.model_validate(bad)

    def test_extra_field_is_silently_ignored(self) -> None:
        """Forward compat: Module A can add fields without breaking B."""
        with_extra = json.loads(json.dumps(VALID_GITHUB_RECORD))
        with_extra["supersedes_artifact_id"] = "art:test:prev"
        with_extra["source"]["pr_number"] = 1234
        rec = ChangeRecord.model_validate(with_extra)
        # Pydantic ignores the extras; the record itself parses fine.
        self.assertEqual(rec.artifact_id, "art:test")
        # The extras are not exposed as attributes.
        self.assertFalse(hasattr(rec, "supersedes_artifact_id"))

    def test_short_commit_sha_accepted(self) -> None:
        """Mock data uses 6-char SHAs; production will use 40-char."""
        rec = ChangeRecord.model_validate(
            {
                **VALID_GITHUB_RECORD,
                "source": {**VALID_GITHUB_RECORD["source"], "commit_sha": "abc123"},
            }
        )
        self.assertEqual(rec.source.commit_sha, "abc123")

    def test_default_heading_path_is_empty_list(self) -> None:
        bad = json.loads(json.dumps(VALID_GITHUB_RECORD))
        del bad["span"]["heading_path"]
        rec = ChangeRecord.model_validate(bad)
        self.assertEqual(rec.span.heading_path, [])


# --- 3. Source discriminated union ----------------------------------------


class SourceUnionTests(unittest.TestCase):

    def test_github_arm_constructible(self) -> None:
        s = GithubSource(
            type="github",
            repo="OWASP/wstg",
            commit_sha="abc123",
            committed_at="2026-05-29T00:00:00Z",
        )
        self.assertEqual(s.type, "github")

    def test_rss_arm_constructible(self) -> None:
        s = RssSource(
            type="rss",
            feed_url="https://example.com/feed.xml",
            post_guid="post-1",
        )
        self.assertEqual(s.type, "rss")


# --- 4. compute_content_hash ---------------------------------------------


class ContentHashTests(unittest.TestCase):

    def test_hash_format(self) -> None:
        h = hashing.compute_content_hash("hello world")
        self.assertEqual(len(h), 64)
        self.assertEqual(h, h.lower())
        # All hex
        int(h, 16)  # raises ValueError if not hex

    def test_hash_determinism(self) -> None:
        a = hashing.compute_content_hash("Authentication should use MFA")
        b = hashing.compute_content_hash("Authentication should use MFA")
        self.assertEqual(a, b)

    def test_normalization_collapses_trailing_whitespace(self) -> None:
        a = hashing.compute_content_hash("line one   \nline two   ")
        b = hashing.compute_content_hash("line one\nline two")
        self.assertEqual(a, b)

    def test_normalization_collapses_crlf(self) -> None:
        a = hashing.compute_content_hash("a\r\nb\r\nc")
        b = hashing.compute_content_hash("a\nb\nc")
        self.assertEqual(a, b)

    def test_normalization_collapses_prose_runs(self) -> None:
        a = hashing.compute_content_hash("foo   bar  baz")
        b = hashing.compute_content_hash("foo bar baz")
        self.assertEqual(a, b)

    def test_normalization_strips_leading_trailing_blank_lines(self) -> None:
        a = hashing.compute_content_hash("\n\nbody\n\n")
        b = hashing.compute_content_hash("body")
        self.assertEqual(a, b)

    def test_normalization_preserves_code_fence_internal_whitespace(self) -> None:
        with_fence = "intro\n\n```python\nx  =  1\n```\n\nouter"
        without_fence = "intro\n\nx = 1\n\nouter"
        # The fence preserves internal "x  =  1"; the un-fenced one collapses.
        # Hashes MUST differ.
        a = hashing.compute_content_hash(with_fence)
        b = hashing.compute_content_hash(without_fence)
        self.assertNotEqual(a, b)

    def test_normalize_is_idempotent(self) -> None:
        original = "  Hello\r\n\r\nWorld   \n\n"
        once = hashing.normalize_text(original)
        twice = hashing.normalize_text(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
