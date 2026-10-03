"""Cross-standard control-name seeding.

Match a chunk's ``Section:`` title (and body head) against hub **control**
titles — ``Node.section`` / ``CRE.name`` — and return CRE ids whose names
overlap. Used to seed the C.1 allowlist when the section looks like a control
already described under ASVS, Cheat Sheets, CCM, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "owasp",
        "top",
        "broken",
        "failure",
        "failures",
        "security",
        "application",
        "section",
        "standard",
        "source",
        "control",
        "controls",
        "requirement",
        "verify",
        "ensure",
    }
)


def _tokens(text: str) -> Set[str]:
    words = [
        t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if t not in _STOP
    ]
    stems: Set[str] = set()
    for w in words:
        stems.add(w)
        for suf in ("ic", "ies", "es", "s", "ing", "tion", "ment"):
            if len(w) > len(suf) + 4 and w.endswith(suf):
                stems.add(w[: -len(suf)])
    return stems


def _overlap(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = set(a & b)
    for x in a:
        for y in b:
            if len(x) >= 5 and len(y) >= 5 and (x in y or y in x):
                inter.add(x)
    return len(inter) / len(a | b)


def section_title_from_text(text: str) -> str:
    m = _SECTION_LINE.search(text or "")
    if m:
        return m.group(1).strip()
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or re.match(
            r"^(Standard|Source|Section-ID|Section|Version):", s, re.I
        ):
            continue
        return s[:160]
    return ""


@dataclass(frozen=True)
class ControlNameIndex:
    """Inverted-ish list of (title tokens, cre hub keys) for fuzzy control match."""

    entries: Tuple[Tuple[FrozenSet[str], str, Tuple[str, ...]], ...]
    #: Minimum Jaccard-ish score to keep a hit.
    min_score: float = 0.22
    top_k: int = 15

    def seed_for_text(self, text: str) -> List[str]:
        """CRE hub keys best-first by title overlap (may be empty)."""
        title = section_title_from_text(text)
        query = _tokens(title)
        if len(query) < 2:
            # Fall back to a bit of body if title is useless.
            body = " ".join(
                ln
                for ln in (text or "").splitlines()
                if not re.match(
                    r"^(Standard|Source|Section-ID|Section|Version):", ln, re.I
                )
            )[:400]
            query = _tokens(body)
        if len(query) < 2:
            return []

        scored: List[Tuple[float, str]] = []
        seen: Set[str] = set()
        for tokens, _label, cre_keys in self.entries:
            score = _overlap(query, set(tokens))
            if score < self.min_score:
                continue
            for cid in cre_keys:
                if cid and cid not in seen:
                    scored.append((score, cid))
                    seen.add(cid)
        scored.sort(reverse=True)
        return [cid for _, cid in scored[: self.top_k]]


def build_control_name_index(session: Any) -> ControlNameIndex:
    """Index Node.section + CRE.name → CRE id/external_id from the hub graph."""
    from application.database.db import CRE, Links, Node

    # cre_id -> list of title strings
    titles_by_cre: Dict[str, List[str]] = {}
    keys_by_cre: Dict[str, Set[str]] = {}

    def _add(cre_uuid: str, ext: str, title: str) -> None:
        if not cre_uuid or not title or len(title.strip()) < 4:
            return
        titles_by_cre.setdefault(cre_uuid, []).append(title.strip())
        # Hub embeddings + CE texts are keyed by CRE UUID — never seed external_id.
        keys_by_cre.setdefault(cre_uuid, set()).add(cre_uuid)

    for cre_id, ext, node_section, node_name in (
        session.query(CRE.id, CRE.external_id, Node.section, Node.name)
        .join(Links, Links.cre == CRE.id)
        .join(Node, Node.id == Links.node)
        .all()
    ):
        if node_section:
            _add(cre_id, ext or "", str(node_section))
        # Skip using bare standard names ("ASVS") as control titles.
        if node_name and len(str(node_name).split()) >= 3:
            _add(cre_id, ext or "", str(node_name))

    for cre_id, ext, name in session.query(CRE.id, CRE.external_id, CRE.name).all():
        if name:
            _add(cre_id, ext or "", str(name))

    entries: List[Tuple[FrozenSet[str], str, Tuple[str, ...]]] = []
    for cre_uuid, titles in titles_by_cre.items():
        # One entry per distinct title (keeps scoring honest).
        for title in sorted(set(titles)):
            toks = frozenset(_tokens(title))
            if len(toks) < 2:
                continue
            keys = tuple(sorted(keys_by_cre.get(cre_uuid, {cre_uuid})))
            entries.append((toks, title[:80], keys))

    return ControlNameIndex(entries=tuple(entries))


def prefer_ids_first(
    preferred: Sequence[str],
    ordered: Sequence[str],
    *,
    limit: int = 8,
    lead: int = 2,
) -> List[str]:
    """Stable: up to ``lead`` preferred CRE ids first, then the rest of ``ordered``."""
    out: List[str] = []
    seen: Set[str] = set()
    for cid in preferred:
        if cid and cid not in seen:
            # Keep preferred even if not in ordered (edition seed may outrank retrieve).
            seen.add(cid)
            out.append(cid)
        if len(out) >= lead:
            break
    for cid in ordered:
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
        if len(out) >= limit:
            break
    return out[:limit]


def prefer_audit_ids(
    audit: Any,
    preferred: Sequence[str],
    *,
    lead: int = 2,
    inject_missing: bool = False,
) -> Any:
    """Reorder ``candidates`` and ``reranked`` so preferred CRE ids lead (B2 grain).

    When ``inject_missing`` is True, preferred ids present only on the vector
    shortlist (dropped by CE top-N) are injected into ``reranked`` from
    ``candidates`` — used for the grounded shortlist judge so B2's rerank-top-2
    gate sees the picks. Default False keeps prior A+B behavior (reorder only).
    """
    if not preferred or audit is None:
        return audit
    lead_ids = [c for c in preferred if c][:lead]
    if not lead_ids:
        return audit

    cand_by_id = {
        c.cre_id: c
        for c in (getattr(audit, "candidates", None) or [])
        if getattr(c, "cre_id", None)
    }

    def _reorder(
        cands: Sequence[Any],
        *,
        allow_inject: bool = False,
    ) -> List[Any]:
        by_id = {c.cre_id: c for c in (cands or []) if getattr(c, "cre_id", None)}
        head: List[Any] = []
        for cid in lead_ids:
            c = by_id.get(cid)
            if c is None and allow_inject:
                c = cand_by_id.get(cid)
                if c is not None and getattr(c, "score_rerank", None) is None:
                    score = float(getattr(c, "score_vector", None) or 0.0)
                    c = c.model_copy(update={"score_rerank": score})
            if c is not None:
                head.append(c)
        seen = {c.cre_id for c in head}
        rest = [c for c in (cands or []) if c.cre_id not in seen]
        return head + rest

    updates: Dict[str, Any] = {}
    if getattr(audit, "candidates", None):
        updates["candidates"] = _reorder(audit.candidates)
    if getattr(audit, "reranked", None):
        updates["reranked"] = _reorder(
            audit.reranked, allow_inject=inject_missing
        )
    elif inject_missing and lead_ids:
        # Empty CE list: still surface preferred from the vector shortlist.
        updates["reranked"] = _reorder([], allow_inject=True)
    if not updates:
        return audit
    return audit.model_copy(update=updates)


__all__ = [
    "ControlNameIndex",
    "build_control_name_index",
    "prefer_audit_ids",
    "prefer_ids_first",
    "section_title_from_text",
]
