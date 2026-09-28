from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from datetime import datetime, timezone

from application.utils.harvester.chunk_record_builder import ChunkRecordBuilder
from application.utils.harvester.chunk_record_validator import (
    ChunkRecordValidator,
    ingest_record_to_payload,
)
from application.utils.harvester.chunker import ChunkInfo
from application.utils.harvester.models import (
    Document,
    HeadingNode,
    Locator,
    SourceInfo,
)
from application.utils.noise_filter.schemas import ChangeRecord


class ChunkRecordBuilderTests(unittest.TestCase):
    def _document(self, text: str, headings: list[HeadingNode]) -> Document:
        return Document(
            schema_version="0.2.0",
            artifact_id="art:OWASP/ASVS:README.md",
            pipeline_run_id="run-1",
            text=text,
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha="abc1234deadbeef",
                committed_at=datetime(2026, 2, 1, 1, 0, 0, tzinfo=timezone.utc),
            ),
            locator=Locator(
                kind="repo_path",
                id="README.md",
                path="README.md",
            ),
            heading_structure=headings,
        )

    def test_builds_change_record_shaped_payload(self) -> None:
        text = "# Root\n\nFirst paragraph."
        document = self._document(
            text,
            [HeadingNode(level=1, text="Root", start_line=1, end_line=3)],
        )
        chunk = ChunkInfo(text=text, start_char_idx=0, end_char_idx=len(text))
        records = ChunkRecordBuilder().build(document, [chunk])
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.chunk_id, "chk:art:OWASP/ASVS:README.md:0")
        self.assertEqual(record.pipeline_run_id, "run-1")
        self.assertEqual(record.source_repo, "OWASP/ASVS")
        self.assertEqual(record.locator_path, "README.md")
        self.assertEqual(record.span.heading_path, ["Root"])
        self.assertTrue(record.text.startswith("Standard: ASVS\n"))
        self.assertIn("Source: README.md\n", record.text)
        self.assertIn("Section: Root\n", record.text)
        self.assertIn("First paragraph.", record.text)

        ChunkRecordValidator().validate(record)
        payload = ingest_record_to_payload(record)
        ChangeRecord.model_validate(payload)

    def test_prefixes_section_id_from_filename(self) -> None:
        text = "# Broken Access Control\n\nDeny by default."
        document = Document(
            schema_version="0.2.0",
            artifact_id="art:B2/owasp_top10_2025:A01",
            pipeline_run_id="run-1",
            text=text,
            source=SourceInfo(
                type="github",
                repository="B2/owasp_top10_2025",
                commit_sha="abc1234",
                committed_at=datetime(2026, 2, 1, 1, 0, 0, tzinfo=timezone.utc),
            ),
            locator=Locator(
                kind="repo_path",
                id="b2/owasp_top10_2025/A01.txt",
                path="b2/owasp_top10_2025/A01.txt",
            ),
            heading_structure=[
                HeadingNode(
                    level=1, text="Broken Access Control", start_line=1, end_line=3
                )
            ],
        )
        chunk = ChunkInfo(text=text, start_char_idx=0, end_char_idx=len(text))
        record = ChunkRecordBuilder().build(document, [chunk])[0]
        self.assertIn("Standard: owasp_top10_2025", record.text)
        self.assertIn("Version: 2025", record.text)
        self.assertIn("Section-ID: A01", record.text)
        self.assertIn("Section: Broken Access Control", record.text)

    def test_indexes_multiple_chunks(self) -> None:
        text = "AAAA\n\nBBBB"
        document = self._document(text, [])
        chunks = [
            ChunkInfo(text="AAAA\n\n", start_char_idx=0, end_char_idx=6),
            ChunkInfo(text="BBBB", start_char_idx=6, end_char_idx=10),
        ]
        records = ChunkRecordBuilder().build(document, chunks)
        self.assertEqual(records[0].span.index, 0)
        self.assertEqual(records[0].span.total, 2)
        self.assertEqual(records[1].span.index, 1)
        self.assertEqual(records[1].chunk_id, "chk:art:OWASP/ASVS:README.md:1")

    def test_requirement_extract_chunk_keeps_single_section_id(self) -> None:
        """Do not re-scrape heading/path ids over a clean extractor prefix."""
        body = (
            "Source: V1.1.2\n"
            "Section-ID: V1.1.2\n"
            "Section: Verify that output encoding is applied.\n\n"
            "Verify that output encoding is applied."
        )
        document = Document(
            schema_version="0.2.0",
            artifact_id="art:OWASP/ASVS:0x10-V1.md",
            pipeline_run_id="run-1",
            text="# V1 Encoding\n\n## V1.1 Architecture\n\n" + body,
            source=SourceInfo(
                type="github",
                repository="OWASP/ASVS",
                commit_sha="abc1234deadbeef",
                committed_at=datetime(2026, 2, 1, 1, 0, 0, tzinfo=timezone.utc),
            ),
            locator=Locator(
                kind="repo_path",
                id="0x10-V1.md",
                path="5.0/en/0x10-V1-Encoding-and-Sanitization.md",
            ),
            heading_structure=[
                HeadingNode(level=1, text="V1 Encoding", start_line=1, end_line=10),
                HeadingNode(
                    level=2, text="V1.1 Architecture", start_line=3, end_line=10
                ),
            ],
        )
        chunk = ChunkInfo(text=body, start_char_idx=0, end_char_idx=len(body))
        record = ChunkRecordBuilder().build(document, [chunk])[0]
        sid_lines = [
            ln for ln in record.text.splitlines() if ln.startswith("Section-ID:")
        ]
        # Outer enricher may add Standard/Version/Source, but Section-ID stays one.
        self.assertEqual(len(sid_lines), 1)
        self.assertEqual(sid_lines[0], "Section-ID: V1.1.2")
        self.assertNotIn("V1.1,", record.text)
        self.assertNotIn("5.0,", record.text)


if __name__ == "__main__":
    unittest.main()
