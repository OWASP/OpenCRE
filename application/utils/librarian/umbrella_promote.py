"""Umbrella / exact-name promotion for Module C suggestions.

B: exact (or near-exact) ``Section:`` title ↔ ``CRE.name`` → pin as preferred.
A: when ≥2 shortlist CREs share an ``InternalLinks`` parent (Contains), promote
that parent CRE into the preferred lead so umbrella gold beats leaf cosine.
Title-gated single-leaf→parent: also promote a parent covering ≥1 child when the
parent name shares a significant token with the Section title.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from application.utils.librarian.control_name_seed import section_title_from_text

_META = re.compile(
    r"^(Standard|Version|Source|Section-ID|Section)\s*:",
    re.I,
)

_PROMOTE_CAP = 4


def _norm_name(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    return re.sub(r"\s+", " ", s)


def _significant_tokens(text: str) -> Set[str]:
    return {t for t in _norm_name(text).split() if len(t) >= 4}


def _tokens_overlap(a: Set[str], b: Set[str]) -> bool:
    """Exact token intersect, or significant substring (config ⊂ misconfiguration)."""
    if a & b:
        return True
    for x in a:
        for y in b:
            if x in y or y in x:
                return True
    return False


def _token_f1(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if not inter:
        return 0.0
    prec = inter / len(ta)
    rec = inter / len(tb)
    return 2.0 * prec * rec / (prec + rec)


@dataclass(frozen=True)
class ExactNameIndex:
    """Normalized CRE.name → hub CRE UUID (embeddings-keyed)."""

    name_to_cre: Mapping[str, Tuple[str, ...]]

    def match_for_text(self, text: str) -> List[str]:
        title = section_title_from_text(text)
        # Prefer last segment of "a > b > title" heading paths.
        if " > " in title:
            title = title.rsplit(" > ", 1)[-1].strip()
        key = _norm_name(title)
        if not key or len(key) < 4:
            return []
        exact = list(self.name_to_cre.get(key, ()))
        if exact:
            return exact
        # Near-exact: CRE name equals title or title equals CRE name as substring
        # only when both sides are short umbrella phrases (≤ 6 tokens).
        title_toks = key.split()
        if len(title_toks) > 6:
            return []
        ranked: List[Tuple[float, int, str, str]] = []
        seen: Set[str] = set()
        for name, cids in self.name_to_cre.items():
            name_toks = name.split()
            if len(name_toks) > 6:
                continue
            if not (name == key or name in key or key in name):
                continue
            score = _token_f1(name, key)
            for cid in cids:
                if cid in seen:
                    continue
                seen.add(cid)
                # Higher F1 first; then shorter CRE name (umbrella over leaves).
                ranked.append((-score, len(name), name, cid))
        ranked.sort()
        return [cid for _, _, _, cid in ranked[:5]]


@dataclass(frozen=True)
class ParentIndex:
    """Child CRE UUID → parent (group) CRE UUIDs from InternalLinks Contains."""

    child_to_parents: Mapping[str, Tuple[str, ...]]
    parent_names: Mapping[str, str] = field(default_factory=dict)

    def promote_for_shortlist(
        self,
        cre_ids: Sequence[str],
        *,
        section_title: str = "",
    ) -> List[str]:
        """Promote shared parents (≥2) and title-overlapping parents (≥1)."""
        counts: Counter[str] = Counter()
        for cid in cre_ids:
            for parent in self.child_to_parents.get(cid, ()):
                if parent:
                    counts[parent] += 1
        title_toks = _significant_tokens(section_title)
        out: List[str] = []
        for parent, n in counts.most_common():
            if parent in out:
                continue
            if n >= 2:
                out.append(parent)
            elif n >= 1 and title_toks:
                pname = self.parent_names.get(parent, "")
                if _tokens_overlap(_significant_tokens(pname), title_toks):
                    out.append(parent)
            if len(out) >= _PROMOTE_CAP:
                break
        return out


def build_exact_name_index(session: Any) -> ExactNameIndex:
    from application.database.db import CRE

    mapping: Dict[str, List[str]] = {}
    for cre_id, name in session.query(CRE.id, CRE.name).all():
        if not cre_id or not name:
            continue
        key = _norm_name(str(name))
        if len(key) < 4:
            continue
        mapping.setdefault(key, []).append(cre_id)
    return ExactNameIndex(
        name_to_cre={k: tuple(v) for k, v in mapping.items()},
    )


def build_parent_index(session: Any) -> ParentIndex:
    from application.database.db import CRE, InternalLinks

    child_to_parents: Dict[str, Set[str]] = {}
    parent_ids: Set[str] = set()
    rows = session.query(
        InternalLinks.group, InternalLinks.cre, InternalLinks.type
    ).all()
    for group, cre, link_type in rows:
        if not group or not cre or group == cre:
            continue
        # Contains: group contains cre (parent → child). Skip unknown types lightly.
        lt = (link_type or "").lower()
        if lt and lt != "contains":
            continue
        child_to_parents.setdefault(cre, set()).add(group)
        parent_ids.add(group)

    parent_names: Dict[str, str] = {}
    if parent_ids:
        for cre_id, name in (
            session.query(CRE.id, CRE.name).filter(CRE.id.in_(parent_ids)).all()
        ):
            if cre_id and name:
                parent_names[cre_id] = str(name)

    return ParentIndex(
        child_to_parents={k: tuple(sorted(v)) for k, v in child_to_parents.items()},
        parent_names=parent_names,
    )


def merge_preferred(
    *groups: Sequence[str],
    limit: int = 8,
) -> List[str]:
    """Stable dedupe: earlier groups win."""
    out: List[str] = []
    seen: Set[str] = set()
    for group in groups:
        for cid in group:
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
            if len(out) >= limit:
                return out
    return out


__all__ = [
    "ExactNameIndex",
    "ParentIndex",
    "build_exact_name_index",
    "build_parent_index",
    "merge_preferred",
]
