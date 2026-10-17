"""Two-level digest: per-document claims (bulk model) -> per-standard overview.

Level 1 claims carry a verbatim quote that must occur in the source; claims whose
quote cannot be found are dropped. Level 2 reads only verified level-1 output and
must cite document paths that exist.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from application.utils.comprehension.sources import SourceDoc

LlmFn = Callable[[str, str], str]

DOC_SYSTEM = (
    "You read ONE document from an open-source security standard repository and "
    "extract what it states. Respond with JSON only: "
    '{"summary": "<2-4 sentences>", "claims": [{"statement": "<self-contained '
    'fact, name the standard/practice it is about>", "quote": "<verbatim '
    'sentence or phrase from the document supporting it>"}]}. '
    "Prefer facts about STRUCTURE (levels, categories, counts, scope, editions, "
    "how parts relate) and definitions. State the edition/version the document describes when it says so. "
    "Never use outside knowledge. At most 25 claims. "
    "If the document has no substantive content return an empty claims list."
)

OVERVIEW_SYSTEM = (
    "You are given verified per-document summaries and claims for ONE standard or "
    "resource. Write what a newcomer needs to understand its overall structure. "
    "Respond with JSON only: "
    '{"overview": "<one paragraph>", "claims": [{"statement": "<self-contained '
    "fact about structure/scope/levels/counts, precise about WHAT is counted and "
    'WHERE (e.g. per practice vs overall)>", "sources": ["<document path>", ...]}]}. '
    "Combine information across documents; do not invent anything not supported by "
    "the given material; every claim must list the document paths it relies on. "
    "When documents describe different versions or editions, state the latest version's facts "
    "and say which version each fact belongs to; never mix versions in one claim. At most 25 claims."
)


@dataclass
class Claim:
    statement: str
    sources: List[str]
    quote: Optional[str] = None


@dataclass
class DocDigest:
    path: str
    summary: str
    claims: List[Claim] = field(default_factory=list)
    dropped: int = 0


@dataclass
class StandardDigest:
    repo: str
    overview: str
    claims: List[Claim]
    docs: List[DocDigest]


def parse_json(text: str) -> Dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return {}
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    return out if isinstance(out, dict) else {}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`>#|]", "", s or "")).strip().lower()


def quote_supported(quote: str, text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 12 and q in _norm(text)


def digest_doc(doc: SourceDoc, llm: LlmFn, *, max_chars: int = 400_000) -> DocDigest:
    data = parse_json(llm(DOC_SYSTEM, f"Path: {doc.path}\n\n{doc.text[:max_chars]}"))
    claims: List[Claim] = []
    dropped = 0
    for c in data.get("claims") or []:
        if not isinstance(c, dict):
            continue
        stmt, quote = str(c.get("statement") or "").strip(), str(c.get("quote") or "")
        if stmt and quote_supported(quote, doc.text):
            claims.append(Claim(stmt, [doc.path], quote))
        else:
            dropped += 1
    return DocDigest(doc.path, str(data.get("summary") or "").strip(), claims, dropped)


def digest_standard(
    repo: str,
    docs: List[SourceDoc],
    bulk_llm: LlmFn,
    overview_llm: LlmFn,
    *,
    workers: int = 8,
    max_overview_chars: int = 3_000_000,
) -> StandardDigest:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        digests = list(pool.map(lambda d: digest_doc(d, bulk_llm), docs))
    digests = [d for d in digests if d.summary or d.claims]
    parts: List[str] = []
    for d in digests:
        lines = [f"## {d.path}", d.summary]
        lines += [f"- {c.statement}" for c in d.claims]
        parts.append("\n".join(lines))
    material = "\n\n".join(parts)[:max_overview_chars]
    data = parse_json(overview_llm(OVERVIEW_SYSTEM, f"Standard: {repo}\n\n{material}"))
    known = {d.path for d in digests}
    claims: List[Claim] = []
    for c in data.get("claims") or []:
        if not isinstance(c, dict):
            continue
        srcs = [s for s in (c.get("sources") or []) if s in known]
        stmt = str(c.get("statement") or "").strip()
        if stmt and srcs:
            claims.append(Claim(stmt, srcs))
    return StandardDigest(
        repo, str(data.get("overview") or "").strip(), claims, digests
    )
