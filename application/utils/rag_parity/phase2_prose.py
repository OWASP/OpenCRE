"""Thin helpers for Standard/Tool embedding prose holes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from application.utils.librarian.embedding_quality import (
    classify_content,
    usable_embedding_text,
)


@dataclass(frozen=True)
class ProseHole:
    node_id: str
    name: str
    reason: str  # empty | junk | stub | missing


def classify_stored_prose(content: Optional[str]) -> str:
    """Return ``prose``, ``empty``, ``junk``, ``stub``, or ``repr``."""
    if content is None or not str(content).strip():
        return "empty"
    body = usable_embedding_text(content)
    if not body:
        # usable_embedding_text emptied junk-only chrome
        kind = classify_content(content)
        return "junk" if kind == "junk" else kind
    return classify_content(body)


def find_prose_holes(
    rows: Sequence[tuple[str, str, Optional[str]]],
) -> List[ProseHole]:
    """``(node_id, name, embeddings_content)`` → holes needing refill."""
    holes: List[ProseHole] = []
    for node_id, name, content in rows:
        kind = classify_stored_prose(content)
        if kind == "prose":
            continue
        holes.append(ProseHole(node_id=node_id, name=name, reason=kind))
    return holes


def prefer_richer_prose(existing: Optional[str], candidate: str) -> str:
    """Keep the better of two blobs for upsert (longer usable prose wins)."""
    a = usable_embedding_text(existing or "") or ""
    b = usable_embedding_text(candidate) or ""
    if classify_content(b) != "prose":
        return existing or ""
    if classify_content(a) != "prose":
        return b
    return b if len(b) > len(a) else a
