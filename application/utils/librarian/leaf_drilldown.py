"""Post-rerank leaf drill-down for Module C.

When a top-ranked CRE is a Contains parent (umbrella / hub), score its children
against the chunk text and promote the best leaf into the suggestion list:

* If the leaf scores higher than the hub → leaf leads, hub stays next.
* Else (hub still wins CE) → still insert the best leaf immediately after the
  hub so specificity is available for exact gold without dropping the umbrella.

Gated by ``CRE_LIBRARIAN_LEAF_DRILLDOWN`` (default on), plus resource grain
(section-count / optional allowlist) and hub fan-out (``min_children``) so
coarse standards do not regress.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from application.utils.librarian.umbrella_promote import ParentIndex

ScoreFn = Callable[[Sequence[Tuple[str, str]]], Sequence[float]]

_DEFAULT_TOP_HUBS = 3
_DEFAULT_MAX_CHILDREN = 32
_DEFAULT_MIN_CHILDREN = 1

# ``asvs`` must not match ``aisvs`` (lookbehind rejects the leading ``i``).
_ASVS_TOKEN_RE = re.compile(r"(?<![a-z])asvs(?![a-z])", re.IGNORECASE)
_STANDARD_LINE_RE = re.compile(r"(?im)^standard:\s*(.+)$")


def resource_family_key(artifact_id: str) -> str:
    """Stable resource family for grain census.

    Examples::

        art:B2/owasp_top10_2025:A01 → art:B2/owasp_top10_2025
        art:OWASP/ASVS:5.0/en/x.md → art:OWASP/ASVS
    """
    art = (artifact_id or "").strip()
    if not art:
        return ""
    if art.startswith("art:B2/"):
        rest = art[len("art:B2/") :]
        stem = rest.split(":", 1)[0]
        return f"art:B2/{stem}" if stem else art
    if art.startswith("art:"):
        parts = art.split(":")
        if len(parts) >= 2 and parts[1]:
            return f"{parts[0]}:{parts[1]}"
    return art


def count_resource_families(
    artifact_ids: Sequence[str],
) -> Mapping[str, int]:
    """Count chunks/sections per ``resource_family_key``."""
    counts: Counter[str] = Counter()
    for art in artifact_ids:
        key = resource_family_key(art)
        if key:
            counts[key] += 1
    return dict(counts)


def resource_is_fine_grained(section_count: int, min_sections: int) -> bool:
    """True when length/grain gate allows drill.

    ``min_sections <= 1`` disables the length gate (always fine-grained).
    """
    if int(min_sections) <= 1:
        return True
    return int(section_count) >= int(min_sections)


def resource_allows_leaf_drilldown(
    *,
    artifact_id: str = "",
    text: str = "",
    allowed: Sequence[str] = (),
) -> bool:
    """Return True when this section's resource may run leaf drill-down.

    Empty ``allowed`` or a lone ``*`` token means no name filter (all OK).
    Tokens match case-insensitively against ``artifact_id`` and any
    ``Standard:`` header line in ``text``. The ``asvs`` token does not match
    ``aisvs``.
    """
    tokens = tuple(t.strip().lower() for t in allowed if t and str(t).strip())
    if not tokens or tokens == ("*",) or "*" in tokens:
        return True

    haystack_parts = [artifact_id or ""]
    for m in _STANDARD_LINE_RE.finditer(text or ""):
        haystack_parts.append(m.group(1))
    haystack = "\n".join(haystack_parts)

    for token in tokens:
        if token == "*":
            return True
        if token == "asvs":
            if _ASVS_TOKEN_RE.search(haystack):
                return True
            continue
        # Word-ish boundary so short tokens do not false-positive inside longer ids.
        pat = re.compile(
            rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
            re.IGNORECASE,
        )
        if pat.search(haystack):
            return True
    return False


def apply_leaf_drilldown(
    cre_ids: Sequence[str],
    query: str,
    *,
    parent_index: Optional[ParentIndex],
    cre_texts: Mapping[str, str],
    score_fn: ScoreFn,
    top_hubs: int = _DEFAULT_TOP_HUBS,
    max_children: int = _DEFAULT_MAX_CHILDREN,
    min_children: int = _DEFAULT_MIN_CHILDREN,
    require_beat_hub: bool = False,
    hub_first: bool = False,
    keep_hub_in_top2: bool = False,
) -> List[str]:
    """Return ``cre_ids`` with Contains-children promoted for specificity.

    By default (``require_beat_hub=False``) the best child is always attached
    next to a hub top-hit — even when the hub's CE score is higher — because
    umbrella-tolerant product metrics still see the hub, while exact leaf gold
    needs the child present. Set ``require_beat_hub=True`` to only promote when
    the child strictly outscores the hub.

    ``hub_first=True`` always keeps the hub ahead of the attached leaf (leaf
    as specificity #2). ``keep_hub_in_top2=True`` ensures each drilled hub
    remains among the first two ids after all attaches (product-d1 safety).

    ``min_children`` skips Contains hubs with fewer than K children (fan-out
    gate). Soft-fail: missing texts, empty children, or scoring errors leave
    that hub unchanged.
    """
    if not cre_ids or parent_index is None:
        return list(cre_ids)

    parent_to_children = getattr(parent_index, "parent_to_children", None) or {}
    if not parent_to_children:
        return list(cre_ids)

    need = max(1, int(min_children))
    out: List[str] = list(cre_ids)
    drilled_hubs: List[str] = []
    hubs_seen = 0
    for hub in list(cre_ids):
        if hubs_seen >= top_hubs:
            break
        children = tuple(parent_to_children.get(hub) or ())
        if len(children) < need:
            continue
        hubs_seen += 1
        if hub not in cre_texts:
            continue

        scored_ids: List[str] = [hub]
        for child in children:
            if child in cre_texts and child not in scored_ids:
                scored_ids.append(child)
            if len(scored_ids) > max_children:
                break
        if len(scored_ids) == 1:
            continue

        pairs = [(query, cre_texts[cid]) for cid in scored_ids]
        try:
            scores = [float(s) for s in score_fn(pairs)]
        except Exception:
            continue
        if len(scores) != len(scored_ids):
            continue

        # Best among children only (index 0 is the hub).
        child_idxs = list(range(1, len(scored_ids)))
        best_i = max(child_idxs, key=lambda i: scores[i])
        best_id = scored_ids[best_i]
        hub_score = scores[0]
        child_beats = scores[best_i] > hub_score
        if require_beat_hub and not child_beats:
            continue

        out = [cid for cid in out if cid != best_id]
        try:
            hub_pos = out.index(hub)
        except ValueError:
            out.insert(0, best_id)
            drilled_hubs.append(hub)
            continue
        if child_beats and not hub_first:
            # Leaf leads; keep hub immediately after.
            out.insert(hub_pos, best_id)
        else:
            # Hub preferred by CE, or hub_first — attach leaf as specificity #2.
            out.insert(hub_pos + 1, best_id)
        drilled_hubs.append(hub)

    if keep_hub_in_top2 and drilled_hubs:
        # Ensure each drilled hub remains in the scored top-2 window.
        head = out[:2]
        for hub in drilled_hubs:
            if hub in head:
                continue
            # Prefer: [hub, leaf...] or [leaf, hub, ...] if leaf already leads.
            if hub in out:
                out = [cid for cid in out if cid != hub]
            if out and out[0] != hub:
                # Keep current #1; place hub at #2.
                out.insert(1, hub)
            else:
                out.insert(0, hub)
            head = out[:2]

    return out


__all__ = [
    "apply_leaf_drilldown",
    "count_resource_families",
    "resource_allows_leaf_drilldown",
    "resource_family_key",
    "resource_is_fine_grained",
    "ScoreFn",
]
