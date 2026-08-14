import unittest

from application.utils.harvester.chunk_record_builder import (
    ChunkRecordBuilder,
)
from application.utils.harvester.chunker import ChunkInfo
from application.utils.harvester.models import (
    Document,
    HeadingNode,
    Locator,
    SourceInfo,
)


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
                commit_sha="abc123",
                committed_at=None,
            ),
            locator=Locator(
                kind="repo_path",
                id="README.md",
                path="README.md",
            ),
            heading_structure=headings,
        )

    def test_builds_chunk_record(self):
        text = "# Root\n\nFirst paragraph."

        document = self._document(
            text,
            [
                HeadingNode(
                    level=1,
                    text="Root",
                    start_line=1,
                    end_line=3,
                )
            ],
        )

        chunk = ChunkInfo(
            text=text,
            start_char_idx=0,
            end_char_idx=len(text),
        )

        records = ChunkRecordBuilder().build(
            document,
            [chunk],
        )

        self.assertEqual(len(records), 1)

        record = records[0]

        self.assertEqual(
            record.artifact_id,
            document.artifact_id,
        )

        self.assertEqual(
            record.text,
            text,
        )

        self.assertEqual(
            record.span.index,
            0,
        )

        self.assertEqual(
            record.span.total,
            1,
        )

        self.assertEqual(
            record.span.heading_path,
            ["Root"],
        )

        self.assertEqual(
            record.span.start_char_idx,
            0,
        )

        self.assertEqual(
            record.span.end_char_idx,
            len(text),
        )

        self.assertEqual(
            record.span.start_line,
            1,
        )

        self.assertEqual(
            record.span.end_line,
            3,
        )

    def test_heading_path_follows_chunk_start(self):
        text = "# Root\n\nroot content\n\n## Child\n\nchild content"

        document = self._document(
            text,
            [
                HeadingNode(
                    level=1,
                    text="Root",
                    start_line=1,
                    end_line=7,
                ),
                HeadingNode(
                    level=2,
                    text="Child",
                    start_line=5,
                    end_line=7,
                ),
            ],
        )

        root_end = text.index("## Child")

        chunks = [
            ChunkInfo(
                text=text[:root_end],
                start_char_idx=0,
                end_char_idx=root_end,
            ),
            ChunkInfo(
                text=text[root_end:],
                start_char_idx=root_end,
                end_char_idx=len(text),
            ),
        ]

        records = ChunkRecordBuilder().build(
            document,
            chunks,
        )

        self.assertEqual(
            records[0].span.heading_path,
            ["Root"],
        )

        self.assertEqual(
            records[1].span.heading_path,
            ["Root", "Child"],
        )

    def test_line_ranges_are_derived_from_character_offsets(self):
        text = "one\ntwo\nthree\nfour"

        document = self._document(text, [])

        chunks = [
            ChunkInfo(
                text="two\nthree",
                start_char_idx=4,
                end_char_idx=13,
            )
        ]

        records = ChunkRecordBuilder().build(
            document,
            chunks,
        )

        self.assertEqual(
            records[0].span.start_line,
            2,
        )

        self.assertEqual(
            records[0].span.end_line,
            3,
        )

    def test_chunk_ids_are_deterministic(self):
        text = "# Root\n\nContent"

        document = self._document(
            text,
            [
                HeadingNode(
                    level=1,
                    text="Root",
                    start_line=1,
                    end_line=3,
                )
            ],
        )

        chunk = ChunkInfo(
            text=text,
            start_char_idx=0,
            end_char_idx=len(text),
        )

        builder = ChunkRecordBuilder()

        first = builder.build(document, [chunk])
        second = builder.build(document, [chunk])

        self.assertEqual(
            first[0].chunk_id,
            second[0].chunk_id,
        )

    def test_chunk_ids_include_heading_path_and_content_hash(self):
        text = "# Root\n\nContent"

        document = self._document(
            text,
            [
                HeadingNode(
                    level=1,
                    text="Root",
                    start_line=1,
                    end_line=3,
                )
            ],
        )

        chunk = ChunkInfo(
            text=text,
            start_char_idx=0,
            end_char_idx=len(text),
        )

        record = ChunkRecordBuilder().build(
            document,
            [chunk],
        )[0]

        self.assertTrue(
            record.chunk_id.startswith("chk:art:OWASP/ASVS:README.md:Root:")
        )

    def test_empty_heading_path_is_allowed(self):
        text = "Plain text without headings."

        document = self._document(text, [])

        chunk = ChunkInfo(
            text=text,
            start_char_idx=0,
            end_char_idx=len(text),
        )

        record = ChunkRecordBuilder().build(
            document,
            [chunk],
        )[0]

        self.assertEqual(
            record.span.heading_path,
            [],
        )


if __name__ == "__main__":
    unittest.main()
