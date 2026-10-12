"""Batch pairwise + source-grounding into one LLM call when both flags are on.

Cuts latency/cost vs sequential ``pairwise_vote`` then ``source_grounding``.
Single-flag paths still use the original modules. LLM/parse failures fail open.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from application.utils.librarian.pairwise_vote import (
    parse_pairwise_vote,
    pairwise_blocks_auto_link,
    pairwise_vote_enabled,
)
from application.utils.librarian.schemas import ReasonCode
from application.utils.librarian.source_grounding import (
    grounding_blocks_auto_link,
    parse_grounding_verdict,
    source_grounding_enabled,
)

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_batched_fail_closed(
    raw: str, cre_a: str, cre_b: str
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(choice, verdict)``; either may be None on parse failure."""
    try:
        data = json.loads(_strip_fences(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    choice = parse_pairwise_vote(json.dumps(data), cre_a, cre_b)
    verdict = parse_grounding_verdict(json.dumps(data))
    return choice, verdict


def build_batched_prompt(
    query_text: str,
    cre_a: Mapping[str, Any],
    cre_b: Mapping[str, Any],
) -> tuple:
    system = (
        "You are a grounded CRE judge for OpenCRE. "
        "Given a standards section and exactly two candidate CREs: "
        "(1) choose which better matches the section, or neither if both are "
        "weak/wrong; (2) for Candidate A only, decide whether the section text "
        "supports linking to it. "
        'Return ONLY JSON: {"choice": "<cre_id_a|cre_id_b|neither>", '
        '"verdict": "supported"|"contradicted"|"insufficient"}.'
    )
    user = (
        "Section:\n"
        f"{(query_text or '').strip()}\n\n"
        f"Candidate A (rank-1 / proposed auto-link): "
        f"{json.dumps(dict(cre_a), ensure_ascii=False)}\n"
        f"Candidate B: {json.dumps(dict(cre_b), ensure_ascii=False)}\n"
    )
    return system, user


def evaluate_fail_closed_levers(
    query_text: str,
    cre_ids: Sequence[str],
    *,
    candidate_meta: Sequence[Mapping[str, Any]],
    llm_fn: Optional[LlmFn],
) -> Optional[ReasonCode]:
    """Return a demote reason, or None to keep the auto-link.

    When both pairwise and grounding are enabled and ≥2 CRE ids are present,
    issues a single batched LLM call. Otherwise uses the single-lever helpers.
    """
    pairwise_on = pairwise_vote_enabled()
    grounding_on = source_grounding_enabled()
    if not pairwise_on and not grounding_on:
        return None
    if llm_fn is None:
        return None

    ids: List[str] = [str(c).strip() for c in cre_ids if str(c).strip()]
    by_id = {
        str(m.get("cre_id") or "").strip(): m
        for m in candidate_meta
        if str(m.get("cre_id") or "").strip()
    }

    if pairwise_on and grounding_on and len(ids) >= 2:
        cre_a, cre_b = ids[0], ids[1]
        meta_a = by_id.get(cre_a) or {"cre_id": cre_a}
        meta_b = by_id.get(cre_b) or {"cre_id": cre_b}
        system, user = build_batched_prompt(query_text, meta_a, meta_b)
        try:
            raw = llm_fn(system, user)
        except Exception:  # noqa: BLE001
            logger.warning("batched fail-closed LLM failed; fail open", exc_info=True)
            return None
        choice, verdict = parse_batched_fail_closed(raw, cre_a, cre_b)
        if choice is None and verdict is None:
            return None
        if choice is not None and (choice == "neither" or choice != cre_a):
            return ReasonCode.pairwise_disagree
        if verdict in ("contradicted", "insufficient"):
            return ReasonCode.source_unsupported
        return None

    if pairwise_on and pairwise_blocks_auto_link(
        query_text, cre_ids, candidate_meta=candidate_meta, llm_fn=llm_fn
    ):
        return ReasonCode.pairwise_disagree

    if grounding_on:
        top = ids[0] if ids else ""
        cre_meta = by_id.get(top) or {"cre_id": top}
        if grounding_blocks_auto_link(query_text, cre_meta, llm_fn=llm_fn):
            return ReasonCode.source_unsupported

    return None


__all__ = [
    "build_batched_prompt",
    "evaluate_fail_closed_levers",
    "parse_batched_fail_closed",
]
