"""Docling + LlamaIndex chunking for Module A.

``strategy: docling`` in ``ChunkingConfig`` routes here. LlamaIndex wraps
Docling's reader/node parser; we map nodes back to ``ChunkInfo`` so the rest of
the harvester (record builder → ``harvest_input``) stays unchanged.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from application.utils.harvester.models import ChunkInfo, Document

if TYPE_CHECKING:
    from application.utils.harvester.schemas import ChunkingConfig

logger = logging.getLogger(__name__)


def chunk_with_docling(
    text: str,
    *,
    document: Optional[Document] = None,
    config: Optional["ChunkingConfig"] = None,
    source_name: str = "document.md",
) -> List[ChunkInfo]:
    """Structure-aware chunks via LlamaIndex DoclingReader + DoclingNodeParser.

    Falls back to Docling ``HybridChunker`` directly if the LlamaIndex path
    fails (import/runtime). Offsets are best-effort against ``text``.
    """
    if not text.strip():
        return []

    try:
        return _chunk_via_llamaindex(text, source_name=source_name)
    except Exception:
        logger.exception(
            "LlamaIndex Docling path failed; falling back to HybridChunker"
        )
        return _chunk_via_hybrid(text, source_name=source_name)


def _chunk_via_llamaindex(text: str, *, source_name: str) -> List[ChunkInfo]:
    from llama_index.node_parser.docling import DoclingNodeParser
    from llama_index.readers.docling import DoclingReader

    suffix = Path(source_name).suffix or ".md"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"ingest{suffix}"
        path.write_text(text, encoding="utf-8")
        reader = DoclingReader(export_type=DoclingReader.ExportType.JSON)
        docs = reader.load_data(str(path))
        nodes = DoclingNodeParser().get_nodes_from_documents(docs)

    return _nodes_to_chunk_infos(text, [n.get_content() for n in nodes])


def _chunk_via_hybrid(text: str, *, source_name: str) -> List[ChunkInfo]:
    from io import BytesIO

    from docling.chunking import HybridChunker
    from docling.document_converter import DocumentConverter
    from docling_core.types.io import DocumentStream

    stream = DocumentStream(
        name=source_name if source_name.endswith(".md") else f"{source_name}.md",
        stream=BytesIO(text.encode("utf-8")),
    )
    dl_doc = DocumentConverter().convert(stream).document
    chunker = HybridChunker()
    pieces = [chunker.contextualize(c) for c in chunker.chunk(dl_doc=dl_doc)]
    return _nodes_to_chunk_infos(text, pieces)


def _nodes_to_chunk_infos(source_text: str, pieces: List[str]) -> List[ChunkInfo]:
    """Map chunk texts onto source offsets (search forward; tolerate serialization drift)."""
    chunks: List[ChunkInfo] = []
    cursor = 0
    for piece in pieces:
        body = (piece or "").strip()
        if not body:
            continue
        # Prefer locating a distinctive mid substring in the source.
        probe = body
        if len(probe) > 80:
            probe = body[len(body) // 4 : len(body) // 4 + 60]
        idx = source_text.find(probe, cursor)
        if idx < 0:
            idx = source_text.find(probe)
        if idx < 0:
            # Synthetic span at cursor so the record builder still gets offsets.
            start = min(cursor, len(source_text))
            end = min(start + max(len(body), 1), len(source_text)) or 1
            if start >= end and source_text:
                start = max(0, len(source_text) - 1)
                end = len(source_text)
            chunks.append(
                ChunkInfo(
                    text=body, start_char_idx=start, end_char_idx=max(end, start + 1)
                )
            )
            cursor = end
            continue
        # Expand to cover the piece length when the probe matched inside source.
        start = idx
        end = min(len(source_text), start + len(body))
        # If contextualized text differs from source, keep piece text but clamp span.
        if end <= start:
            end = min(len(source_text), start + 1)
        chunks.append(ChunkInfo(text=body, start_char_idx=start, end_char_idx=end))
        cursor = end
    return chunks
