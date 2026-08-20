from .chunk_record_builder import ChunkRecordBuilder
from .chunk_record_validator import ChunkRecordValidator
from .chunker import DocumentChunker
from .models import Document, IngestChunkRecord


class DocumentChunkPipeline:
    """
    Runs semantic chunking followed by structure-aware RFC
    chunk-record construction and validation.
    """

    def __init__(
        self,
        chunker: DocumentChunker | None = None,
        record_builder: ChunkRecordBuilder | None = None,
        validator: ChunkRecordValidator | None = None,
    ) -> None:
        self._chunker = chunker or DocumentChunker()
        self._record_builder = record_builder or ChunkRecordBuilder()
        self._validator = validator or ChunkRecordValidator()

    def chunk(self, document: Document) -> list[IngestChunkRecord]:
        chunks = self._chunker.chunk(document.text)

        records = self._record_builder.build(
            document,
            chunks,
        )

        for record in records:
            self._validator.validate(record)

        return records
