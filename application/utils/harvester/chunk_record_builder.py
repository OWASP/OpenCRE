from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from .chunker import DocumentChunker
from .models import ChunkInfo, Document, IngestChunkRecord, SpanInfo

if TYPE_CHECKING:
    from .schemas import ChunkingConfig

# Section ids used by Top10 / API / LLM / K8s / ASVS / AISVS / agentic stubs.
_SECTION_ID_RE = re.compile(
    r"\b("
    r"AAI\d{2}"  # Agentic AI stub (before A\d{2})
    r"|A\d{2}"  # OWASP Top 10
    r"|API\d{1,2}"  # API Top 10
    r"|LLM\d{2}"  # LLM Top 10
    r"|K\d{2}"  # Kubernetes Top 10
    r"|AISVS\d{1,2}"  # AISVS categories
    r"|V?\d+\.\d+(?:\.\d+)?"  # ASVS / numeric
    r")\b",
    re.IGNORECASE,
)


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
        source_name = self._source_filename(document)
        standard = self._standard_name(document)
        version = self._version_id(standard, document)
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
                    text=self._prefixed_text(
                        chunk.text,
                        source_name=source_name,
                        standard=standard,
                        version=version,
                        heading_path=heading_path,
                        locator_path=document.locator.path or document.locator.id or "",
                    ),
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
    def _source_filename(document: Document) -> str:
        path = (document.locator.path or document.locator.id or "").strip()
        if path:
            return path.rsplit("/", 1)[-1]
        return document.artifact_id.rsplit(":", 1)[-1]

    @staticmethod
    def _standard_name(document: Document) -> str:
        repo = (document.source.repository or "").strip()
        if "/" in repo:
            return repo.rsplit("/", 1)[-1]
        if repo:
            return repo
        art = document.artifact_id or ""
        # art:OWASP/ASVS:path or art:B2/owasp_top10_2025:A01
        if art.startswith("art:"):
            body = art[len("art:") :]
            first = body.split(":", 1)[0]
            if "/" in first:
                return first.rsplit("/", 1)[-1]
            return first
        return ""

    @staticmethod
    def _version_id(standard: str, document: Document) -> str:
        """Year or version token for ``Version:`` (e.g. 2025, 4.0, 1.0)."""
        blob = " ".join(
            [
                standard or "",
                document.source.repository or "",
                document.artifact_id or "",
                document.locator.path or "",
            ]
        )
        year = re.search(r"(20\d{2})", blob)
        if year:
            return year.group(1)
        ver = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", blob, re.I)
        if ver:
            return ver.group(1)
        return ""

    @staticmethod
    def _extract_section_ids(*parts: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for part in parts:
            for match in _SECTION_ID_RE.findall(part or ""):
                sid = match.upper() if match[0].isalpha() else match
                if sid not in seen:
                    seen.add(sid)
                    out.append(sid)
        return out

    @staticmethod
    def _prefixed_text(
        text: str,
        *,
        source_name: str,
        standard: str,
        version: str,
        heading_path: list[str],
        locator_path: str,
    ) -> str:
        """Enrich chunk text for Module C retrieval (standard + section identity)."""
        section_ids = ChunkRecordBuilder._extract_section_ids(
            source_name,
            locator_path,
            " ".join(heading_path),
            text[:800],
        )
        lines: list[str] = []
        if standard:
            lines.append(f"Standard: {standard}")
        if version:
            lines.append(f"Version: {version}")
        lines.append(f"Source: {source_name}")
        if section_ids:
            lines.append("Section-ID: " + ", ".join(section_ids[:6]))
        if heading_path:
            lines.append("Section: " + " > ".join(heading_path))
        lines.append("")
        lines.append(text)
        return "\n".join(lines)

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
        n = len(text)
        if n == 0:
            return 1, 1
        start = max(0, min(int(start_char_idx), n - 1))
        end = max(start + 1, min(int(end_char_idx), n))
        start_line = text.count("\n", 0, start) + 1
        end_line = text.count("\n", 0, end - 1) + 1
        return start_line, end_line


def chunk_document(
    document: Document,
    config: Optional["ChunkingConfig"] = None,
) -> list[IngestChunkRecord]:
    chunker = DocumentChunker(config)
    chunks = chunker.chunk(document.text, document=document)
    return ChunkRecordBuilder().build(document, chunks)
