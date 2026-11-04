"""Chunk quality hooks before embeddings upsert."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from application.utils.librarian.embedding_quality import (
    classify_content,
    usable_embedding_text,
)

DEFAULT_MIN_CHARS = 80
DEFAULT_MAX_CHARS = 12000


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str = ""
    meta: dict | None = None


@dataclass(frozen=True)
class QualityReport:
    accepted: List[Chunk]
    rejected: List[tuple[Chunk, str]]


def filter_chunks(
    chunks: Sequence[Chunk],
    *,
    min_chars: int = DEFAULT_MIN_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> QualityReport:
    """Drop empty/junk/stub chunks; truncate overlong accepted prose."""
    accepted: List[Chunk] = []
    rejected: List[tuple[Chunk, str]] = []
    for chunk in chunks:
        body = usable_embedding_text(chunk.text)
        if not body:
            rejected.append((chunk, "empty_or_junk"))
            continue
        kind = classify_content(body)
        if kind != "prose":
            rejected.append((chunk, kind))
            continue
        if len(body) < min_chars:
            rejected.append((chunk, "too_short"))
            continue
        if len(body) > max_chars:
            body = body[:max_chars].rstrip()
        accepted.append(
            Chunk(text=body, source=chunk.source, meta=dict(chunk.meta or {}))
        )
    return QualityReport(accepted=accepted, rejected=rejected)
