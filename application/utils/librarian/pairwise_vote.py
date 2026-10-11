"""Experimental pairwise A-vs-B vote (fail-closed demote to review).

Gated by ``CRE_LIBRARIAN_PAIRWISE_VOTE`` (default off). Runs on top of the
existing shortlist judge: when two CRE candidates remain, ask an LLM which
matches the section (or neither). Disagreement with rank-1 / ``neither`` /
``ambiguous`` forces ``PAIRWISE_DISAGREE`` review. LLM/parse failures fail open
(keep the existing decision).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]


def pairwise_vote_enabled() -> bool:
    return os.environ.get("CRE_LIBRARIAN_PAIRWISE_VOTE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_pairwise_vote(raw: str, cre_a: str, cre_b: str) -> Optional[str]:
    """Return ``cre_a``, ``cre_b``, ``neither``, or None on parse failure."""
    try:
        data = json.loads(_strip_fences(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        choice = str(data.get("choice") or data.get("winner") or "").strip()
    else:
        choice = str(data).strip()
    if not choice:
        return None
    low = choice.lower()
    if low in ("neither", "ambiguous", "none", "tie"):
        return "neither"
    if choice == cre_a or low == cre_a.lower():
        return cre_a
    if choice == cre_b or low == cre_b.lower():
        return cre_b
    return None


def build_pairwise_prompt(
    query_text: str,
    cre_a: Mapping[str, Any],
    cre_b: Mapping[str, Any],
) -> tuple:
    system = (
        "You are a grounded CRE pairwise judge for OpenCRE. "
        "Given a standards section and exactly two candidate CREs, choose which "
        "one better matches the section, or neither if both are weak/wrong. "
        'Return ONLY JSON: {"choice": "<cre_id_a|cre_id_b|neither>"}.'
    )
    user = (
        "Section:\n"
        f"{(query_text or '').strip()}\n\n"
        f"Candidate A: {json.dumps(dict(cre_a), ensure_ascii=False)}\n"
        f"Candidate B: {json.dumps(dict(cre_b), ensure_ascii=False)}\n"
    )
    return system, user


def pairwise_blocks_auto_link(
    query_text: str,
    cre_ids: Sequence[str],
    *,
    candidate_meta: Sequence[Mapping[str, Any]],
    llm_fn: Optional[LlmFn],
) -> bool:
    """True when the vote says do not auto-link top-1."""
    if not pairwise_vote_enabled() or llm_fn is None:
        return False
    ids: List[str] = [str(c).strip() for c in cre_ids if str(c).strip()]
    if len(ids) < 2:
        return False
    cre_a, cre_b = ids[0], ids[1]
    by_id = {
        str(m.get("cre_id") or "").strip(): m
        for m in candidate_meta
        if str(m.get("cre_id") or "").strip()
    }
    meta_a = by_id.get(cre_a) or {"cre_id": cre_a}
    meta_b = by_id.get(cre_b) or {"cre_id": cre_b}
    system, user = build_pairwise_prompt(query_text, meta_a, meta_b)
    try:
        raw = llm_fn(system, user)
    except Exception:  # noqa: BLE001
        logger.warning("pairwise vote LLM failed; fail open", exc_info=True)
        return False
    choice = parse_pairwise_vote(raw, cre_a, cre_b)
    if choice is None:
        return False
    if choice == "neither" or choice != cre_a:
        return True
    return False
