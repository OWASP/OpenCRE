import hashlib
from dataclasses import dataclass

from .models import Document, IngestChunkRecord, SpanInfo
from .chunker import ChunkInfo


@dataclass(slots=True)
class ChunkRecordBuilder:
    """
    Converts semantic ChunkInfo objects into structure-aware
    ingestion chunk records.
    """

    SCHEMA_VERSION = "0.2.0"

    def build(
        self,
        document: Document,
        chunks: list[ChunkInfo],
    ) -> list[IngestChunkRecord]:
        total = len(chunks)

        records: list[IngestChunkRecord] = []

        for index, chunk in enumerate(chunks):
            heading_path = self._heading_path_for_chunk(
                document,
                chunk,
            )

            content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()

            chunk_id = self._chunk_id(
                artifact_id=document.artifact_id,
                heading_path=heading_path,
                start_char_idx=chunk.start_char_idx,
                end_char_idx=chunk.end_char_idx,
                content_hash=content_hash,
            )

            start_line, end_line = self._line_range(
                document.text,
                chunk.start_char_idx,
                chunk.end_char_idx,
            )

            records.append(
                IngestChunkRecord(
                    schema_version=self.SCHEMA_VERSION,
                    chunk_id=chunk_id,
                    artifact_id=document.artifact_id,
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
                )
            )

        return records

    @staticmethod
    def _heading_path_for_chunk(
        document: Document,
        chunk: ChunkInfo,
    ) -> list[str]:
        """
        Determine the Markdown heading hierarchy containing the
        beginning of the chunk.

        A heading is considered active when its range contains
        the chunk's starting line.
        """

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
        """
        Convert zero-based character offsets into one-based
        inclusive line numbers.

        The end offset is treated as exclusive.
        """

        if not 0 <= start_char_idx < end_char_idx <= len(text):
            raise ValueError("Chunk character offsets are outside the source document")

        start_line = (
            text.count(
                "\n",
                0,
                start_char_idx,
            )
            + 1
        )

        end_position = end_char_idx - 1

        end_line = (
            text.count(
                "\n",
                0,
                end_position,
            )
            + 1
        )

        return start_line, end_line

    @staticmethod
    def _chunk_id(
        artifact_id: str,
        heading_path: list[str],
        start_char_idx: int,
        end_char_idx: int,
        content_hash: str,
    ) -> str:
        heading = "/".join(heading_path)

        return (
            f"chk:{artifact_id}:{heading}:"
            f"{start_char_idx}-{end_char_idx}:{content_hash}"
        )
