from cre_logging import get_logger

logger = get_logger(__name__)

from .chunk_record_builder import ChunkRecordBuilder
from .chunk_record_validator import ChunkRecordValidator
from .chunker import DocumentChunker
from .chunk_merger import merge_chunks
from .models import Document, IngestChunkRecord
from .schemas import ChunkingConfig


class DocumentChunkPipeline:
    """
    Runs config-driven chunking, optional A.2 merge, then RFC chunk-record
    construction and validation.
    """

    def __init__(
        self,
        chunking: ChunkingConfig | None = None,
        chunker: DocumentChunker | None = None,
        record_builder: ChunkRecordBuilder | None = None,
        validator: ChunkRecordValidator | None = None,
    ) -> None:
        self._chunking = chunking
        self._chunker = chunker or DocumentChunker(chunking)
        self._record_builder = record_builder or ChunkRecordBuilder()
        self._validator = validator or ChunkRecordValidator()

    def chunk(self, document: Document) -> list[IngestChunkRecord]:
        chunks = self._chunker.chunk(document.text, document=document)
        if self._chunking is not None:
            chunks = merge_chunks(document, chunks, self._chunking)
        records = self._record_builder.build(document, chunks)
        for record in records:
            self._validator.validate(record)
        return records
