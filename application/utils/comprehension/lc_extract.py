"""LangChain-style structured extracts for ask glue (slugs + answer plan).

Uses the cheap helper LLM + JSON schema prompts. Returns ``None`` on failure so
callers keep regex/phrase fallbacks. Does not own ``decide()`` / τ.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]

_SLUG_SYSTEM = (
    "Pick which OWASP project slugs the question is about from the candidate menu. "
    'Return ONLY JSON: {"slugs":["slug-one","slug-two"]}. '
    "Use only slugs from the menu. Empty list if none clearly named. Max "
)


_PLAN_SYSTEM = (
    "Classify how to answer an OWASP/OpenCRE question. Return ONLY JSON with booleans: "
    '{"multipart":false,"people_route":false,"count_route":false,"cre_style":false}. '
    "multipart=true if several distinct questions. "
    "people_route=true if asking who leads/authors/maintainers. "
    "count_route=true if asking how many / totals. "
    "cre_style=true if about CRE mappings, OpenCRE, compare standards, or what's new."
)


def _parse_json_obj(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def extract_project_slugs(
    question: str,
    candidates: Sequence[Tuple[str, str]],
    *,
    limit: int = 3,
    llm: Optional[LlmFn] = None,
) -> Optional[List[str]]:
    """Return ordered slugs from ``candidates`` (slug, alias) or ``None`` on failure.

    ``candidates`` must be non-empty. Only menu slugs are accepted.
    """
    if not question or not candidates:
        return None
    if llm is None:
        from application.utils.comprehension import flags

        llm = flags.helper_llm()
    if llm is None:
        return None
    allowed = {slug: alias for slug, alias in candidates if slug}
    if not allowed:
        return None
    menu = "\n".join(f"- {slug}: {alias}" for slug, alias in list(allowed.items())[:80])
    try:
        raw = llm(
            _SLUG_SYSTEM + f"{limit}.",
            f"Question: {question}\n\nCandidates:\n{menu}",
        )
    except Exception:  # noqa: BLE001
        logger.debug("lc_extract slugs LLM failed", exc_info=True)
        return None
    data = _parse_json_obj(raw)
    if not data:
        return None
    slugs = data.get("slugs")
    if not isinstance(slugs, list):
        return None
    out: List[str] = []
    for item in slugs:
        s = str(item or "").strip()
        if s in allowed and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def extract_answer_plan(
    question: str, *, llm: Optional[LlmFn] = None
) -> Optional[Dict[str, bool]]:
    """Return plan flags or ``None`` on failure."""
    if not (question or "").strip():
        return None
    if llm is None:
        from application.utils.comprehension import flags

        llm = flags.helper_llm()
    if llm is None:
        return None
    try:
        raw = llm(_PLAN_SYSTEM, f"Question: {question}")
    except Exception:  # noqa: BLE001
        logger.debug("lc_extract plan LLM failed", exc_info=True)
        return None
    data = _parse_json_obj(raw)
    if not data:
        return None
    keys = ("multipart", "people_route", "count_route", "cre_style")
    out: Dict[str, bool] = {}
    for k in keys:
        out[k] = bool(data.get(k))
    return out
