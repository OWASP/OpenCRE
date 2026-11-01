"""Experimental source-text grounding (fail-closed demote to review).

Gated by ``CRE_LIBRARIAN_SOURCE_GROUNDING`` (default off). After Module C would
auto-link, ask whether the section text *supports* the chosen CRE's name /
summary. ``contradicted`` / ``insufficient`` → ``SOURCE_UNSUPPORTED`` review.
LLM/parse failures fail open.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable, Mapping, Optional

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]

_VERDICTS = frozenset({"supported", "contradicted", "insufficient"})


def source_grounding_enabled() -> bool:
    return os.environ.get("CRE_LIBRARIAN_SOURCE_GROUNDING", "0").strip().lower() in (
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


def parse_grounding_verdict(raw: str) -> Optional[str]:
    try:
        data = json.loads(_strip_fences(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        verdict = str(data.get("verdict") or data.get("label") or "").strip().lower()
    else:
        verdict = str(data).strip().lower()
    if verdict in _VERDICTS:
        return verdict
    return None


def build_grounding_prompt(query_text: str, cre: Mapping[str, Any]) -> tuple:
    system = (
        "You are a grounding verifier for OpenCRE CRE links. "
        "Decide whether the standards section text supports linking to the "
        "given CRE. Return ONLY JSON: "
        '{"verdict": "supported"|"contradicted"|"insufficient"}.'
    )
    user = (
        "Section:\n"
        f"{(query_text or '').strip()}\n\n"
        f"Proposed CRE:\n{json.dumps(dict(cre), ensure_ascii=False)}\n"
    )
    return system, user


def grounding_blocks_auto_link(
    query_text: str,
    cre: Mapping[str, Any],
    *,
    llm_fn: Optional[LlmFn],
) -> bool:
    """True when verdict is contradicted or insufficient."""
    if not source_grounding_enabled() or llm_fn is None:
        return False
    if not str(cre.get("cre_id") or "").strip():
        return False
    system, user = build_grounding_prompt(query_text, cre)
    try:
        raw = llm_fn(system, user)
    except Exception:  # noqa: BLE001
        logger.warning("source grounding LLM failed; fail open", exc_info=True)
        return False
    verdict = parse_grounding_verdict(raw)
    if verdict is None:
        return False
    return verdict in ("contradicted", "insufficient")
