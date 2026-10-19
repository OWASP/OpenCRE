"""Pick the best agent-lane hit: score margin first, optional constrained LLM.

The LLM may only choose an id from the provided candidate list — it must not
invent entities or expand beyond that set.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, List, Optional, Sequence

from application.utils.owasp_agent.lane_similarity import (
    LaneHit,
    _float_env,
)

CompletionFn = Callable[[Sequence[dict]], str]


def llm_pick_enabled() -> bool:
    raw = (os.environ.get("OWASP_AGENT_LLM_PICK") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _candidate_label(hit: LaneHit, index: int) -> str:
    url = (hit.url or "").strip()
    content = (hit.content or "").strip().splitlines()
    head = content[0] if content else ""
    if len(head) > 160:
        head = head[:157] + "..."
    return f"{index}. score={hit.score:.3f} url={url}\n   {head}"


def _parse_pick_id(raw: str, n: int) -> Optional[int]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "id" in data:
            idx = int(data["id"])
            if 1 <= idx <= n:
                return idx
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    m = re.search(r"\b([1-9][0-9]*)\b", text)
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= n:
            return idx
    return None


def llm_pick_candidate(
    prompt: str,
    candidates: List[LaneHit],
    *,
    completion_fn: CompletionFn,
) -> Optional[LaneHit]:
    """Ask the LLM to pick one candidate id; returns that hit or None."""
    if not candidates:
        return None
    catalog = "\n".join(_candidate_label(h, i + 1) for i, h in enumerate(candidates))
    messages = [
        {
            "role": "system",
            "content": (
                "You select the single most relevant OWASP community metadata "
                "candidate for the user question. Reply with JSON only: "
                '{"id": <number>}. The id must be one of the listed numbers. '
                "Do not invent entities. Do not explain."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question:\n{prompt.strip()}\n\nCandidates:\n{catalog}\n\n"
                'Reply with {"id": N} only.'
            ),
        },
    ]
    try:
        raw = completion_fn(messages)
    except Exception:
        return None
    idx = _parse_pick_id(raw, len(candidates))
    if idx is None:
        return None
    return candidates[idx - 1]


def _url_kind(hit: LaneHit) -> str:
    url = hit.url or ""
    if url.startswith("owasp-agent://evidence/"):
        return "evidence"
    if url.startswith("owasp-agent://meta/"):
        return url[len("owasp-agent://meta/") :].split("/", 1)[0].strip().lower()
    return ""


# Structural / concept cues only — never bare brand tokens (asvs|masvs|samm|…).
# Legitimate "Who leads the OWASP ASVS project?" must still reach Nest project_lookup.
_EVIDENCE_NARROW_RE = re.compile(
    r"\b("
    r"trifecta|exfiltration|prompt injection|"
    r"how many|levels?|maturity|layers?|verification"
    r")\b",
    re.IGNORECASE,
)


def prefers_evidence_narrowing(prompt: str) -> bool:
    """True when the prompt is structure/concept-shaped (not a Nest project ask)."""
    return bool(_EVIDENCE_NARROW_RE.search(prompt or ""))


def is_structure_ask(prompt: str) -> bool:
    """Level / layer / maturity / verification structure questions (Nest-steal risk)."""
    return bool(
        re.search(
            r"\b(how many|levels?|maturity|layers?|verification)\b",
            prompt or "",
            re.IGNORECASE,
        )
    )


def narrow_candidates(prompt: str, candidates: List[LaneHit]) -> List[LaneHit]:
    """When the question clearly targets a kind present in top-k, restrict to it."""
    if not candidates:
        return []
    t = (prompt or "").lower()
    by_kind: dict[str, List[LaneHit]] = {}
    for h in candidates:
        by_kind.setdefault(_url_kind(h), []).append(h)

    # Structural kind cues only (not topic/brand keyword dumps).
    if re.search(r"\bchapters?\b", t) and by_kind.get("chapter"):
        return by_kind["chapter"]
    if re.search(r"\bboard\b", t) and (
        by_kind.get("board_roster") or by_kind.get("board_member")
    ):
        return by_kind.get("board_roster") or by_kind["board_member"]
    # Prefer evidence cards for structure / concept facts over Nest project stage.
    if by_kind.get("evidence") and prefers_evidence_narrowing(prompt):
        return by_kind["evidence"]
    return candidates


def select_agent_hit(
    prompt: str,
    candidates: List[LaneHit],
    *,
    completion_fn: Optional[CompletionFn] = None,
    get_completion_fn: Optional[Callable[[], Optional[CompletionFn]]] = None,
) -> Optional[LaneHit]:
    """Choose a hit by score margin, else constrained LLM pick, else top mid+."""
    if not candidates:
        return None
    t_mid = _float_env("OWASP_AGENT_SIM_MID", 0.65)
    t_low = _float_env("OWASP_AGENT_SIM_LOW", 0.55)
    # Chapter / evidence / board roster: answer on weaker scores (corpus cards).
    t_rescue = _float_env("OWASP_AGENT_SIM_RESCUE", 0.50)
    margin = _float_env("OWASP_AGENT_SIM_MARGIN", 0.05)

    pool = narrow_candidates(prompt, candidates)
    viable = [h for h in pool if h.score >= t_low]
    if not viable:
        # Rescue preferred kinds slightly below t_low.
        rescue_kinds = {"chapter", "evidence", "board_roster"}
        viable = [
            h for h in pool if h.score >= t_rescue and _url_kind(h) in rescue_kinds
        ]
    if not viable:
        return None
    top = viable[0]
    clear = len(viable) == 1 or top.score >= viable[1].score + margin
    kind = _url_kind(top)
    kind_mid = t_rescue if kind in {"chapter", "evidence", "board_roster"} else t_mid
    if clear and top.score >= kind_mid:
        return top

    fn = completion_fn
    if (
        fn is None
        and get_completion_fn is not None
        and llm_pick_enabled()
        and len(viable) >= 2
    ):
        try:
            fn = get_completion_fn()
        except Exception:
            fn = None

    if llm_pick_enabled() and fn is not None and len(viable) >= 2:
        picked = llm_pick_candidate(prompt, viable, completion_fn=fn)
        if picked is not None:
            return picked

    if top.score >= kind_mid:
        return top
    return None


def default_completion_fn() -> Optional[CompletionFn]:
    """Build a LiteLLM completion wrapper when the chat stack is available."""
    try:
        from application.database import db as db_mod
        from application.prompt_client import litellm_router, prompt_client

        database = db_mod.Node_collection()
        from application.utils.comprehension.shared import shared_handler

        handler = shared_handler(database)

        def _complete(messages: Sequence[dict]) -> str:
            resp = litellm_router.completion(
                model=handler.chat_model,
                messages=list(messages),
                client=handler._litellm,
                context="OWASP agent candidate pick",
                temperature=0,
                max_retries=handler._llm_max_retries,
                retry_sleep_seconds=handler._llm_retry_sleep_seconds,
            )
            return litellm_router.extract_content_text(resp)

        return _complete
    except Exception:
        return None
