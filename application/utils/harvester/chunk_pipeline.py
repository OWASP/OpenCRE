from .chunk_record_builder import ChunkRecordBuilder
from .chunker import DocumentChunker
from .models import Document, IngestChunkRecord


class DocumentChunkPipeline:
    """
    Runs semantic chunking followed by structure-aware RFC
    chunk-record construction.
    """

    def __init__(
        self,
        chunker: DocumentChunker | None = None,
        record_builder: ChunkRecordBuilder | None = None,
    ) -> None:
        self._chunker = chunker or DocumentChunker()
        self._record_builder = record_builder or ChunkRecordBuilder()

    def chunk(self, document: Document) -> list[IngestChunkRecord]:
        chunks = self._chunker.chunk(document.text)

        return self._record_builder.build(
            document,
            chunks,
        )
