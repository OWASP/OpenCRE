"""Tests for Module A.2 chunk merge profiles."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from application.utils.harvester.chunk_merger import merge_chunks, requirement_ids
from application.utils.harvester.models import (
    ChunkInfo,
    Document,
    HeadingNode,
    Locator,
    SourceInfo,
)
from application.utils.harvester.schemas import ChunkingConfig


def _doc(text: str, headings: list[HeadingNode] | None = None) -> Document:
    return Document(
        schema_version="0.2.0",
        artifact_id="art:OWASP/Test:x.md",
        pipeline_run_id="test",
        text=text,
        source=SourceInfo(
            type="github",
            repository="OWASP/Test",
            commit_sha="abc",
            committed_at=datetime.now(timezone.utc),
        ),
        locator=Locator(kind="repo_path", id="x.md", path="x.md"),
        heading_structure=headings or [],
    )


class ChunkMergerTests(unittest.TestCase):
    def test_requirement_ids_extracted(self) -> None:
        self.assertEqual(
            requirement_ids("**2.1.1** Verify passwords"), frozenset({"2.1.1"})
        )
        self.assertIn("2.1.1", requirement_ids("V2.1.1 something"))
        self.assertEqual(
            requirement_ids("AC-2 Account Management"), frozenset({"ac-2"})
        )
        self.assertIn("a.5.1", requirement_ids("ISO A.5.1 policies"))
        self.assertIn("3.4", requirement_ids("Req 3.4 Protect stored"))
        self.assertEqual(
            requirement_ids("Requirement 3.4.1 hashing"), frozenset({"3.4.1"})
        )

    def test_requirements_does_not_merge_nist_or_iso_ids(self) -> None:
        t1 = ("AC-2 Account Management. " * 20).strip()
        t2 = ("AC-3 Access Enforcement. " * 20).strip()
        text = t1 + "\n\n" + t2
        mid = len(t1) + 2
        chunks = [
            ChunkInfo(text=t1, start_char_idx=0, end_char_idx=len(t1)),
            ChunkInfo(text=t2, start_char_idx=mid, end_char_idx=len(text)),
        ]
        headings = [
            HeadingNode(level=2, text="Access Control", start_line=1, end_line=99)
        ]
        doc = _doc(text, headings)
        cfg = ChunkingConfig(
            strategy="docling",
            max_tokens=1200,
            overlap_tokens=10,
            merge_profile="requirements",
        )
        out = merge_chunks(doc, chunks, cfg)
        self.assertEqual(len(out), 2)

    def test_none_profile_is_noop(self) -> None:
        text = "aaaa " * 50 + "\n\n" + "bbbb " * 50
        mid = text.index("bbbb")
        chunks = [
            ChunkInfo(text=text[:mid], start_char_idx=0, end_char_idx=mid),
            ChunkInfo(text=text[mid:], start_char_idx=mid, end_char_idx=len(text)),
        ]
        cfg = ChunkingConfig(
            strategy="docling", max_tokens=1200, overlap_tokens=10, merge_profile="none"
        )
        doc = _doc(text)
        out = merge_chunks(doc, chunks, cfg)
        self.assertEqual(len(out), 2)

    def test_requirements_does_not_merge_across_ids(self) -> None:
        t1 = ("Verify 2.1.1 passwords are long. " * 20).strip()
        t2 = ("Verify 2.1.2 passwords allow unicode. " * 20).strip()
        text = t1 + "\n\n" + t2
        mid = len(t1) + 2
        chunks = [
            ChunkInfo(text=t1, start_char_idx=0, end_char_idx=len(t1)),
            ChunkInfo(text=t2, start_char_idx=mid, end_char_idx=len(text)),
        ]
        headings = [
            HeadingNode(
                level=2, text="V2.1 Password Security", start_line=1, end_line=99
            )
        ]
        doc = _doc(text, headings)
        cfg = ChunkingConfig(
            strategy="docling",
            max_tokens=1200,
            overlap_tokens=10,
            merge_profile="requirements",
        )
        out = merge_chunks(doc, chunks, cfg)
        self.assertEqual(len(out), 2)

    def test_narrative_merges_same_heading_crumbs(self) -> None:
        # Same heading, tiny crumbs → one merged chunk under narrative profile.
        a = "Short intro."
        b = "More detail on the same topic."
        text = a + "\n\n" + b
        mid = len(a) + 2
        chunks = [
            ChunkInfo(text=a, start_char_idx=0, end_char_idx=len(a)),
            ChunkInfo(text=b, start_char_idx=mid, end_char_idx=len(text)),
        ]
        headings = [
            HeadingNode(level=2, text="Password Storage", start_line=1, end_line=99)
        ]
        doc = _doc(text, headings)
        cfg = ChunkingConfig(
            strategy="docling",
            max_tokens=1000,
            overlap_tokens=10,
            merge_profile="narrative",
        )
        out = merge_chunks(doc, chunks, cfg)
        self.assertEqual(len(out), 1)
        self.assertIn("Short intro", out[0].text)
        self.assertIn("More detail", out[0].text)

    def test_narrative_merges_h3_under_same_h2(self) -> None:
        text = (
            "## Auth\n\n"
            "### Intro\n\n"
            "First crumb about auth.\n\n"
            "### Detail\n\n"
            "Second crumb still under Auth."
        )
        # Approximate char ranges for two leaves under different ### but same ##.
        first = "First crumb about auth."
        second = "Second crumb still under Auth."
        i1 = text.index(first)
        i2 = text.index(second)
        chunks = [
            ChunkInfo(text=first, start_char_idx=i1, end_char_idx=i1 + len(first)),
            ChunkInfo(text=second, start_char_idx=i2, end_char_idx=i2 + len(second)),
        ]
        headings = [
            HeadingNode(level=2, text="Auth", start_line=1, end_line=20),
            HeadingNode(level=3, text="Intro", start_line=3, end_line=6),
            HeadingNode(level=3, text="Detail", start_line=8, end_line=20),
        ]
        doc = _doc(text, headings)
        cfg = ChunkingConfig(
            strategy="docling",
            max_tokens=1000,
            overlap_tokens=10,
            merge_profile="narrative",
        )
        out = merge_chunks(doc, chunks, cfg)
        self.assertEqual(len(out), 1)

    def test_profile_defaults_on_config(self) -> None:
        req = ChunkingConfig(
            strategy="fixed_size",
            max_tokens=500,
            overlap_tokens=10,
            merge_profile="requirements",
        )
        self.assertTrue(req.split_on_requirement_id)
        self.assertEqual(req.merge_min_tokens, 100)
        nar = ChunkingConfig(
            strategy="fixed_size",
            max_tokens=500,
            overlap_tokens=10,
            merge_profile="narrative",
        )
        self.assertFalse(nar.split_on_requirement_id)
        self.assertEqual(nar.merge_min_tokens, 400)


if __name__ == "__main__":
    unittest.main()
