"""Classify stored Standard/Tool/CRE ``embeddings_content`` quality."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

_JUNK_RE = re.compile(
    r"unauthorized frame window|you have javascript disabled|"
    r"this is a potential security issue,\s*you are being redirected|"
    r"skip to content navigation menu|"
    r"an official website of the united states government",
    re.IGNORECASE,
)
_STUB_CHARS = 80
_BURIED_MARKERS = ("verify that", "discussion", "control:")


@dataclass(frozen=True)
class EmbeddingRow:
    name: str
    content: str


@dataclass(frozen=True)
class FamilyReport:
    name: str
    n: int
    avg_chars: float
    unique_ratio: float
    junk_ratio: float
    stub_ratio: float
    verdict: str


def classify_content(text: str) -> str:
    """Return ``junk``, ``stub``, or ``prose``."""
    body = text or ""
    if _JUNK_RE.search(body):
        return "junk"
    if len(body.strip()) < _STUB_CHARS:
        return "stub"
    return "prose"


def _extract_buried_requirement(text: str) -> str:
    """Pull requirement prose out of a chrome-prefixed page dump."""
    lower = text.lower()
    for needle in _BURIED_MARKERS:
        idx = lower.find(needle)
        if idx >= 0 and len(text) - idx >= _STUB_CHARS:
            return text[idx:].strip()
    return ""


def usable_embedding_text(text: str) -> str:
    """Text safe to use as CRE match description.

    Chrome/frame-buster blobs are junk for retrieval, but ASVS/NIST often bury
    a real requirement after the nav. Prefer that excerpt over the title.
    """
    body = (text or "").strip()
    if not body:
        return ""
    if classify_content(body) != "junk":
        return body
    extracted = _extract_buried_requirement(body)
    if extracted and classify_content(extracted) == "prose":
        return extracted
    return ""


def summarize_families(rows: Sequence[EmbeddingRow]) -> List[FamilyReport]:
    grouped: Dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row.name or "(unnamed)"].append(row.content or "")
    reports: List[FamilyReport] = []
    for name, contents in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        n = len(contents)
        avg = sum(len(c) for c in contents) / n if n else 0.0
        unique = len(set(c.strip() for c in contents))
        unique_ratio = unique / n if n else 0.0
        labels = [classify_content(c) for c in contents]
        junk_ratio = labels.count("junk") / n if n else 0.0
        stub_ratio = labels.count("stub") / n if n else 0.0
        if junk_ratio >= 0.5:
            verdict = "junk"
        elif n >= 5 and unique_ratio <= 0.15:
            verdict = "duplicate"
        elif stub_ratio >= 0.5:
            verdict = "stub"
        else:
            verdict = "prose"
        reports.append(
            FamilyReport(
                name=name,
                n=n,
                avg_chars=avg,
                unique_ratio=unique_ratio,
                junk_ratio=junk_ratio,
                stub_ratio=stub_ratio,
                verdict=verdict,
            )
        )
    return reports


def rows_from_sqlite(path: str) -> Iterable[EmbeddingRow]:
    import sqlite3

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        sql = (
            "SELECT n.name AS name, e.embeddings_content AS content "
            "FROM embeddings e JOIN node n ON n.id = e.node_id "
            "WHERE e.doc_type = 'Standard'"
        )
        for row in conn.execute(sql):
            yield EmbeddingRow(
                name=str(row["name"] or ""), content=str(row["content"] or "")
            )
    finally:
        conn.close()


__all__ = [
    "EmbeddingRow",
    "FamilyReport",
    "classify_content",
    "rows_from_sqlite",
    "summarize_families",
    "usable_embedding_text",
]
