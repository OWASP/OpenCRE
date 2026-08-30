from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from .chunker import DocumentChunker
from .models import ChunkInfo, Document, IngestChunkRecord, SpanInfo

if TYPE_CHECKING:
    from .schemas import ChunkingConfig


@dataclass(slots=True)
class ChunkRecordBuilder:
    """
    Converts ChunkInfo objects into Module-B-facing ingest records.
    """

    SCHEMA_VERSION = "0.2.0"

    def build(
        self,
        document: Document,
        chunks: list[ChunkInfo],
    ) -> list[IngestChunkRecord]:
        total = len(chunks)
        committed_at = document.source.committed_at
        if isinstance(committed_at, datetime):
            if committed_at.tzinfo is None:
                committed_at = committed_at.replace(tzinfo=timezone.utc)
            committed_at_str = committed_at.isoformat().replace("+00:00", "Z")
        else:
            committed_at_str = str(committed_at)

        records: list[IngestChunkRecord] = []
        for index, chunk in enumerate(chunks):
            heading_path = self._heading_path_for_chunk(document, chunk)
            start_line, end_line = self._line_range(
                document.text,
                chunk.start_char_idx,
                chunk.end_char_idx,
            )
            records.append(
                IngestChunkRecord(
                    schema_version=self.SCHEMA_VERSION,
                    chunk_id=f"chk:{document.artifact_id}:{index}",
                    artifact_id=document.artifact_id,
                    pipeline_run_id=document.pipeline_run_id,
                    text=chunk.text,
                    span=SpanInfo(
                        heading_path=heading_path,
                        start_line=start_line,
                        end_line=end_line,
                        index=index,
                        total=total,
                        start_char_idx=chunk.start_char_idx,
                        end_char_idx=chunk.end_char_idx,
                    ),
                    source_type=document.source.type,
                    source_repo=document.source.repository,
                    source_commit_sha=document.source.commit_sha,
                    source_committed_at=committed_at_str,
                    locator_kind=document.locator.kind,
                    locator_id=document.locator.id,
                    locator_path=document.locator.path,
                )
            )
        return records

    @staticmethod
    def _heading_path_for_chunk(
        document: Document,
        chunk: ChunkInfo,
    ) -> list[str]:
        start_line, _ = ChunkRecordBuilder._line_range(
            document.text,
            chunk.start_char_idx,
            chunk.end_char_idx,
        )
        active = [
            heading
            for heading in document.heading_structure
            if heading.start_line <= start_line <= heading.end_line
        ]
        active.sort(key=lambda heading: heading.start_line)
        path: list[str] = []
        for heading in active:
            while len(path) >= heading.level:
                path.pop()
            path.append(heading.text)
        return path

    @staticmethod
    def _line_range(
        text: str,
        start_char_idx: int,
        end_char_idx: int,
    ) -> tuple[int, int]:
        if not 0 <= start_char_idx < end_char_idx <= len(text):
            raise ValueError("Chunk character offsets are outside the source document")
        start_line = text.count("\n", 0, start_char_idx) + 1
        end_position = end_char_idx - 1
        end_line = text.count("\n", 0, end_position) + 1
        return start_line, end_line


def chunk_document(
    document: Document,
    config: Optional["ChunkingConfig"] = None,
) -> list[IngestChunkRecord]:
    chunker = DocumentChunker(config)
    chunks = chunker.chunk(document.text, document=document)
    return ChunkRecordBuilder().build(document, chunks)
