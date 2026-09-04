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

        ChunkRecordValidator().validate(record)
        payload = ingest_record_to_payload(record)
        ChangeRecord.model_validate(payload)

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


if __name__ == "__main__":
    unittest.main()
