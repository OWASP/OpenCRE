"""Phase 3: citation synthesizer — strip sentences without citations."""

from __future__ import annotations

import re
from typing import List, Sequence

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CITE = re.compile(r"\[(\d+)\]|\((?:CRE|Source)\s*[:#]?\s*[^)]+\)", re.I)
# synthesize SYSTEM asks models to end with [1][3]; treat that as citing the whole answer.
_TRAILING_CITES = re.compile(r"(?:\s*\[\d+\])+\s*$")
_CITE_ONLY = re.compile(r"^(?:\s*\[\d+\])+\s*$")


def sentences_with_citations(text: str) -> List[str]:
    parts = [
        p.strip() for p in _SENTENCE_SPLIT.split((text or "").strip()) if p.strip()
    ]
    return [p for p in parts if _CITE.search(p)]


def strip_uncited_sentences(text: str) -> str:
    draft = (text or "").strip()
    if not draft:
        return draft
    # End-cite style: prose then trailing [n] markers — keep the full answer.
    if _TRAILING_CITES.search(draft):
        body = _TRAILING_CITES.sub("", draft).rstrip()
        if body and not any(
            _CITE.search(p) for p in _SENTENCE_SPLIT.split(body) if p.strip()
        ):
            return draft
    kept = sentences_with_citations(draft)
    cleaned = " ".join(kept)
    # Never collapse a prose answer to citation markers only.
    if cleaned and _CITE_ONLY.match(cleaned) and not _CITE_ONLY.match(draft):
        return draft
    return cleaned


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
