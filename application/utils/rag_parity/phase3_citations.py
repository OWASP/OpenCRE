"""Phase 3: citation synthesizer — strip sentences without citations."""

from __future__ import annotations

import re
from typing import List, Sequence

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CITE = re.compile(r"\[(\d+)\]|\((?:CRE|Source)\s*[:#]?\s*[^)]+\)", re.I)


def sentences_with_citations(text: str) -> List[str]:
    parts = [
        p.strip() for p in _SENTENCE_SPLIT.split((text or "").strip()) if p.strip()
    ]
    return [p for p in parts if _CITE.search(p)]


def strip_uncited_sentences(text: str) -> str:
    kept = sentences_with_citations(text)
    return " ".join(kept)


def synthesize_cited_answer(
    draft: str,
    *,
    enabled: bool,
    sources: Sequence[str] = (),
) -> str:
    """When enabled, drop uncited sentences; optionally append source footnote."""
    if not enabled:
        return draft
    cleaned = strip_uncited_sentences(draft)
    if sources and cleaned:
        footnotes = " ".join(f"[{i}] {s}" for i, s in enumerate(sources, start=1))
        return f"{cleaned}\n\nSources: {footnotes}"
    return cleaned
