from .models import IngestChunkRecord


class ChunkRecordValidator:
    """
    Validates RFC-facing ingestion chunk records.
    """

    def validate(self, record: IngestChunkRecord) -> None:
        if not record.schema_version.strip():
            raise ValueError("Chunk record schema_version must not be empty")

        if not record.chunk_id.startswith("chk:"):
            raise ValueError("Chunk record chunk_id must start with 'chk:'")

        if not record.artifact_id.strip():
            raise ValueError("Chunk record artifact_id must not be empty")

        if not record.text.strip():
            raise ValueError("Chunk record text must not be empty")

        span = record.span

        if span.index is None or span.total is None:
            raise ValueError("Chunk record span must contain index and total")

        if span.index < 0:
            raise ValueError("Chunk record span.index must be non-negative")

        if span.total <= 0:
            raise ValueError("Chunk record span.total must be positive")

        if span.index >= span.total:
            raise ValueError("Chunk record span.index must be less than total")

        if span.start_char_idx is None or span.end_char_idx is None:
            raise ValueError("Chunk record span must contain character offsets")

        if span.start_char_idx >= span.end_char_idx:
            raise ValueError(
                "Chunk record start_char_idx must be less than end_char_idx"
            )

        if span.start_line <= 0:
            raise ValueError("Chunk record start_line must be positive")

        if span.end_line < span.start_line:
            raise ValueError("Chunk record end_line must not precede start_line")
