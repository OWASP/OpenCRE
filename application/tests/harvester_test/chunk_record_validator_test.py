import unittest

from application.utils.harvester.chunk_record_validator import (
    ChunkRecordValidator,
)
from application.utils.harvester.models import (
    IngestChunkRecord,
    SpanInfo,
)


def valid_record() -> IngestChunkRecord:
    return IngestChunkRecord(
        schema_version="0.2.0",
        chunk_id="chk:art:OWASP/OpenCRE:README.md:abc123",
        artifact_id="art:OWASP/OpenCRE:README.md",
        text="Some valid chunk content.",
        span=SpanInfo(
            heading_path=["Introduction"],
            start_line=1,
            end_line=2,
            index=0,
            total=1,
            start_char_idx=0,
            end_char_idx=25,
        ),
    )


class ChunkRecordValidatorTests(unittest.TestCase):
    def test_valid_record(self):
        ChunkRecordValidator().validate(valid_record())

    def test_empty_text_is_rejected(self):
        record = valid_record()
        record.text = "   "

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)

    def test_invalid_chunk_id_is_rejected(self):
        record = valid_record()
        record.chunk_id = "invalid-id"

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)

    def test_missing_span_index_is_rejected(self):
        record = valid_record()
        record.span.index = None

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)

    def test_index_outside_total_is_rejected(self):
        record = valid_record()
        record.span.index = 1
        record.span.total = 1

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)

    def test_invalid_character_range_is_rejected(self):
        record = valid_record()
        record.span.start_char_idx = 25
        record.span.end_char_idx = 10

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)

    def test_invalid_line_range_is_rejected(self):
        record = valid_record()
        record.span.start_line = 5
        record.span.end_line = 3

        with self.assertRaises(ValueError):
            ChunkRecordValidator().validate(record)


if __name__ == "__main__":
    unittest.main()
