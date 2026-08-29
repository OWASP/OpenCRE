import unittest
from datetime import datetime, timezone

from application.utils.harvester.chunker import ChunkInfo, DocumentChunker
from application.utils.harvester.models import (
    Document,
    HeadingNode,
    Locator,
    SourceInfo,
)
from application.utils.harvester.schemas import ChunkingConfig


def _doc(text: str, headings: list[HeadingNode] | None = None) -> Document:
    return Document(
        schema_version="0.2.0",
        artifact_id="art:OWASP/ASVS:README.md",
        pipeline_run_id="run-1",
        text=text,
        source=SourceInfo(
            type="github",
            repository="OWASP/ASVS",
            commit_sha="abc1234",
            committed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        locator=Locator(kind="repo_path", id="README.md", path="README.md"),
        heading_structure=headings or [],
    )


class DocumentChunkerTests(unittest.TestCase):
    def test_empty_document_returns_no_chunks(self) -> None:
        chunker = DocumentChunker(
            ChunkingConfig(strategy="fixed_size", max_tokens=100, overlap_tokens=10)
        )
        self.assertEqual(chunker.chunk(""), [])

    def test_whitespace_document_returns_no_chunks(self) -> None:
        chunker = DocumentChunker(
            ChunkingConfig(strategy="fixed_size", max_tokens=100, overlap_tokens=10)
        )
        self.assertEqual(chunker.chunk("   \n\n  "), [])

    def test_markdown_heading_keeps_sections_separate(self) -> None:
        text = "# Auth\n\nAAA\n\n# Storage\n\nBBB\n"
        document = _doc(
            text,
            [
                HeadingNode(level=1, text="Auth", start_line=1, end_line=3),
                HeadingNode(level=1, text="Storage", start_line=5, end_line=7),
            ],
        )
        chunker = DocumentChunker(
            ChunkingConfig(
                strategy="markdown_heading", max_tokens=500, overlap_tokens=10
            )
        )
        chunks = chunker.chunk(text, document=document)
        self.assertGreaterEqual(len(chunks), 2)
        joined = "".join(c.text for c in chunks)
        self.assertIn("AAA", joined)
        self.assertIn("BBB", joined)
        # Storage content must not start before its heading offset.
        storage_start = text.index("# Storage")
        storage_chunks = [c for c in chunks if c.start_char_idx >= storage_start]
        self.assertTrue(any("BBB" in c.text for c in storage_chunks))

    def test_fixed_size_respects_budget(self) -> None:
        text = ("word " * 200).strip()
        chunker = DocumentChunker(
            ChunkingConfig(strategy="fixed_size", max_tokens=20, overlap_tokens=5)
        )
        chunks = chunker.chunk(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertIsInstance(chunk, ChunkInfo)
            self.assertLessEqual(len(chunk.text), 20 * 4 + 5)


if __name__ == "__main__":
    unittest.main()
