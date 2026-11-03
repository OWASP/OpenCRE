"""Optional LlamaIndex / Docling ingest → existing embeddings tables.

Never creates a second VectorStoreIndex as source of truth. Callers inject a
writer that upserts into OpenCRE ``Embeddings`` / harvest rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol, Sequence

from application.utils.rag_parity.phase2_chunk_quality import (
    Chunk,
    QualityReport,
    filter_chunks,
)
from application.utils.rag_parity.flags import RagParityFlags, load_flags

logger = logging.getLogger(__name__)


class EmbeddingWriter(Protocol):
    def upsert_prose(self, *, node_id: str, text: str, source: str) -> None: ...


@dataclass(frozen=True)
class IngestResult:
    written: int
    rejected: int
    backend: str


LoaderFn = Callable[[str], Sequence[Chunk]]


def _plain_text_loader(path: str) -> List[Chunk]:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return [Chunk(text=text, source=path)]


def try_docling_loader(path: str) -> List[Chunk]:
    """Optional Docling conversion; raises ImportError if unavailable."""
    from docling.document_converter import DocumentConverter  # type: ignore

    converter = DocumentConverter()
    result = converter.convert(path)
    text = result.document.export_to_markdown()
    return [Chunk(text=text, source=path, meta={"loader": "docling"})]


def try_llamaindex_pipeline_chunks(
    path: str,
    *,
    transformations: Optional[Sequence[object]] = None,
) -> List[Chunk]:
    """Optional LI IngestionPipeline — returns chunks only; no VectorStoreIndex SoT."""
    from llama_index.core import SimpleDirectoryReader  # type: ignore
    from llama_index.core.ingestion import IngestionPipeline  # type: ignore
    from llama_index.core.node_parser import SentenceSplitter  # type: ignore

    docs = SimpleDirectoryReader(input_files=[path]).load_data()
    pipeline = IngestionPipeline(
        transformations=list(transformations or [SentenceSplitter()])
    )
    nodes = pipeline.run(documents=docs)
    out: List[Chunk] = []
    for node in nodes:
        text = getattr(node, "get_content", lambda: str(node))()
        out.append(Chunk(text=text, source=path, meta={"loader": "llamaindex"}))
    return out


def load_chunks_for_path(
    path: str,
    flags: Optional[RagParityFlags] = None,
    *,
    loader: Optional[LoaderFn] = None,
) -> List[Chunk]:
    """Resolve loader by flag: injected > Docling > LI > plain text."""
    if loader is not None:
        return list(loader(path))
    cfg = flags or load_flags()
    if cfg.use_docling:
        try:
            return try_docling_loader(path)
        except Exception:  # noqa: BLE001
            logger.debug("Docling loader failed; falling back", exc_info=True)
    if cfg.ingest_pipeline:
        try:
            return try_llamaindex_pipeline_chunks(path)
        except Exception:  # noqa: BLE001
            logger.debug("LI ingest failed; falling back", exc_info=True)
    return _plain_text_loader(path)


def ingest_path_to_writer(
    path: str,
    *,
    node_id: str,
    writer: EmbeddingWriter,
    flags: Optional[RagParityFlags] = None,
    loader: Optional[LoaderFn] = None,
) -> IngestResult:
    """Load → quality filter → write accepted prose into existing tables."""
    cfg = flags or load_flags()
    if not cfg.ingest_pipeline and loader is None and not cfg.use_docling:
        # Explicit opt-in unless a test injects a loader.
        chunks = _plain_text_loader(path) if loader is None else list(loader(path))
        backend = "plain"
    else:
        chunks = load_chunks_for_path(path, cfg, loader=loader)
        backend = "flagged"
    report: QualityReport = filter_chunks(chunks)
    written = 0
    for chunk in report.accepted:
        writer.upsert_prose(node_id=node_id, text=chunk.text, source=chunk.source)
        written += 1
    return IngestResult(written=written, rejected=len(report.rejected), backend=backend)
