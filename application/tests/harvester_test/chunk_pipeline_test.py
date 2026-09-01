import unittest
from unittest.mock import Mock

from application.utils.harvester.chunk_pipeline import DocumentChunkPipeline
from application.utils.harvester.models import Document, IngestChunkRecord


class DocumentChunkPipelineTests(unittest.TestCase):
    def test_invalid_record_is_rejected_before_return(self):
        document = Mock(spec=Document)
        document.text = "Some document text."

        chunker = Mock()
        chunker.chunk.return_value = ["chunk"]

        record_builder = Mock()
        invalid_record = Mock(spec=IngestChunkRecord)
        record_builder.build.return_value = [invalid_record]

        validator = Mock()
        validator.validate.side_effect = ValueError("invalid chunk record")

        pipeline = DocumentChunkPipeline(
            chunker=chunker,
            record_builder=record_builder,
            validator=validator,
        )

        with self.assertRaisesRegex(ValueError, "invalid chunk record"):
            pipeline.chunk(document)

        validator.validate.assert_called_once_with(invalid_record)


if __name__ == "__main__":
    unittest.main()
