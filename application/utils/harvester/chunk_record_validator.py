from application.utils.noise_filter.schemas import ChangeRecord

from .models import IngestChunkRecord


class ChunkRecordValidator:
    """
    Validates RFC-facing ingestion chunk records against Module B's contract.
    """

    def validate(self, record: IngestChunkRecord) -> None:
        if not record.schema_version.strip():
            raise ValueError("Chunk record schema_version must not be empty")

        if not record.chunk_id.startswith("chk:"):
            raise ValueError("Chunk record chunk_id must start with 'chk:'")

        if not record.artifact_id.strip():
            raise ValueError("Chunk record artifact_id must not be empty")

        if not record.pipeline_run_id.strip():
            raise ValueError("Chunk record pipeline_run_id must not be empty")

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

        if span.start_char_idx < 0 or span.end_char_idx < 0:
            raise ValueError("Chunk record character offsets must be non-negative")

        if span.start_char_idx >= span.end_char_idx:
            raise ValueError(
                "Chunk record start_char_idx must be less than end_char_idx"
            )

        if span.start_line <= 0:
            raise ValueError("Chunk record start_line must be positive")

        if span.end_line < span.start_line:
            raise ValueError("Chunk record end_line must not precede start_line")

        # Canonical gate: must round-trip Module B ChangeRecord.
        ChangeRecord.model_validate(ingest_record_to_payload(record))


def ingest_record_to_payload(record: IngestChunkRecord) -> dict:
    """Serialize an ingest record to the Module A → B JSON payload shape."""
    return {
        "schema_version": record.schema_version,
        "chunk_id": record.chunk_id,
        "artifact_id": record.artifact_id,
        "pipeline_run_id": record.pipeline_run_id,
        "text": record.text,
        "span": {
            "index": record.span.index,
            "total": record.span.total,
            "heading_path": list(record.span.heading_path),
            "start_char_idx": record.span.start_char_idx,
            "end_char_idx": record.span.end_char_idx,
            "start_line": record.span.start_line,
            "end_line": record.span.end_line,
        },
        "source": {
            "type": record.source_type,
            "repo": record.source_repo,
            "commit_sha": record.source_commit_sha,
            "committed_at": record.source_committed_at,
        },
        "locator": {
            "kind": record.locator_kind,
            "id": record.locator_id,
            "path": record.locator_path,
        },
    }
