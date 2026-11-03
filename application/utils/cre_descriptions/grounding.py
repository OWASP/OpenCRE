"""Filter linked Standard/Tool prose used to ground CRE descriptions."""

from __future__ import annotations

from typing import List, Sequence

from application.utils.librarian.embedding_quality import (
    classify_content,
    usable_embedding_text,
)


def usable_grounding_leaves(prose_list: Sequence[str]) -> List[str]:
    """Return prose suitable for grounding; skip empty, stub, junk, and chrome."""
    leaves: List[str] = []
    for raw in prose_list:
        body = usable_embedding_text(raw)
        if not body or classify_content(body) != "prose":
            continue
        leaves.append(body)
    return leaves


def grounding_snippet(
    leaves: Sequence[str],
    neighbour_names: Sequence[str],
    max_chars: int = 400,
) -> str:
    """Short human-readable grounding for the approval table."""
    parts: List[str] = []
    for leaf in leaves:
        blob = (leaf or "").strip()
        if blob:
            parts.append(blob)
    neighbours = [n.strip() for n in neighbour_names if (n or "").strip()]
    if neighbours:
        parts.append("neighbours: " + "; ".join(neighbours))
    text = " | ".join(parts)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
