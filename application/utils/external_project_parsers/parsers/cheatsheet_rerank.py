"""
RFC Workstream E — LLM rationale generation for cheat-sheet CRE links.

See: docs/rfc/cheatsheets-llm-autonomous-mapping-rfc.md, section 5
("Workstream E: LLM Re-Rank and Decision Graph (LangGraph)").

## Why this module looks different from the original Workstream E scope

The RFC originally scoped Workstream E as "LLM re-rank the top-k candidates
from Workstream D." Since then, retrieval *and* reranking for the mapping
pipeline have consolidated onto Module C ("The Librarian",
``application/utils/librarian/``): C.1 retrieves candidates, C.2 reranks them
with a cross-encoder, C.3 calibrates confidence, and C.4 decides + emits an
RFC ``LinkProposal`` or ``ReviewItem`` (see PR #944's closing comment and
PR #991). Building a second, LLM-based reranker on top of that would compete
with C.2 rather than add anything.

What Module C's merged code does *not* do, and structurally cannot do with a
cross-encoder, is explain its pick in prose. Concretely:

* ``schemas.ProposedLink.rationale: Optional[str]`` is a real field in the
  RFC wire contract.
* ``emitter.py``'s ``_proposed_links()`` sets ``rationale=None`` on every
  single link, unconditionally -- there is no code path anywhere in Module C
  that populates it.
* ``decision_engine.decide()`` only ever surfaces a single top-1
  ``cre_id`` per chunk (``candidate_cre_ids[:1]``), so the scope of "explain
  the pick" is one candidate, not a shortlist.

This module fills exactly that gap: given the section text and the one CRE
Module C already chose (id, text, and its calibrated score), it asks an LLM
for a short, grounded, one-sentence rationale -- the same LLM-reasoning
capability Workstream E was always meant to contribute, retargeted at the
one place in the pipeline that's actually missing it, instead of duplicating
C.2's scoring job.

This is a discussion-first proposal, not a fait accompli: wiring
``generate_link_rationale`` into ``application/utils/librarian/emitter.py``
is left to the Module C maintainers to decide on, since that module is an
actively developed, separately owned GSoC deliverable. This file stays
self-contained and does not import or modify anything under
``application/utils/librarian/``.

## Design notes (mostly carried over from the original implementation)

* The LLM call is dependency-injected as ``llm_rationale_fn`` -- the same
  seam pattern used throughout this codebase (``ai_client`` in
  ``embed_alignment.py``, ``score_fn`` in ``librarian/cross_encoder.py``).
  Production defaults to a lazily-imported LiteLLM call; tests inject a
  deterministic stub, keeping the whole flow hermetically testable.
* A small LangGraph flow (generate -> format | generate -> fallback ->
  format) still backs the public entrypoint, per the RFC's "Decision Graph
  (LangGraph)" framing -- now scoped to one node's worth of real work
  (generate a rationale) plus its fallback, rather than a multi-stage
  rerank pipeline that would have duplicated C.2/C.3/C.4.
* Never raises on LLM failure -- falls back to a short, honest, templated
  rationale ("Retrieval/rerank score S; LLM explanation unavailable.") so a
  cheat sheet's link is never blocked or degraded by an LLM hiccup.
* ``classify_confidence`` is kept as a small, independently useful utility
  for human-facing review UIs (Module C's own ``decide()`` thresholds
  numerically and has no notion of confidence *bands*), but is no longer on
  the path that decides whether something links or gets reviewed -- that
  call is Module C's alone.
"""

from __future__ import annotations

import json
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from functools import partial
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypedDict

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confidence thresholds (RFC section 11 bootstrap defaults; recalibrate via env)
# ---------------------------------------------------------------------------
_HIGH_THRESHOLD_ENV_VAR = "CRE_CHEATSHEET_RERANK_HIGH_THRESHOLD"
_MEDIUM_THRESHOLD_ENV_VAR = "CRE_CHEATSHEET_RERANK_MEDIUM_THRESHOLD"
_DEFAULT_HIGH_THRESHOLD = "0.85"
_DEFAULT_MEDIUM_THRESHOLD = "0.70"

# Identifiers persisted into RationaleTrace for the RFC audit trail (mirrors
# RETRIEVER_NAME / RERANKER_NAME conventions in application/utils/librarian/).
RATIONALE_GENERATOR_NAME = "llm-cheatsheet-rationale-generator"
PROMPT_VERSION = "v2"

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MODEL_ENV_VAR = "CRE_CHEATSHEET_RERANK_MODEL"
DEFAULT_MODEL_FALLBACK = "gemini/gemini-2.5-flash"

REASON_MAX_LENGTH = 400


class RerankError(ValueError):
    """Base class for this module's construction/usage failures."""


def _resolve_threshold(env_var: str, default: str) -> float:
    raw = os.environ.get(env_var, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise RerankError(f"{env_var}={raw!r} is not a valid float") from exc
    if not (0.0 <= value <= 1.0):
        raise RerankError(f"{env_var}={value!r} must be in [0, 1]")
    return value


def classify_confidence(score: float) -> str:
    """
    Map a 0-1 score to a confidence band ("high" | "medium" | "low").

    Independent utility for human-facing review UIs -- Module C's own
    ``decide()`` thresholds numerically and has no notion of bands; this
    does not feed back into that decision. Thresholds are the RFC's
    bootstrap defaults (high >= 0.85, medium >= 0.70), recalibratable via
    ``CRE_CHEATSHEET_RERANK_HIGH_THRESHOLD`` /
    ``CRE_CHEATSHEET_RERANK_MEDIUM_THRESHOLD``, re-read on every call.
    """
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise RerankError(f"score must be a number, got {score!r}")
    if not (0.0 <= float(score) <= 1.0):
        raise RerankError(f"score must be in [0, 1], got {score!r}")

    high = _resolve_threshold(_HIGH_THRESHOLD_ENV_VAR, _DEFAULT_HIGH_THRESHOLD)
    medium = _resolve_threshold(_MEDIUM_THRESHOLD_ENV_VAR, _DEFAULT_MEDIUM_THRESHOLD)
    if high < medium:
        raise RerankError(
            f"{_HIGH_THRESHOLD_ENV_VAR}={high!r} must be >= "
            f"{_MEDIUM_THRESHOLD_ENV_VAR}={medium!r}"
        )

    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RationaleTrace:
    """Audit metadata captured for every rationale-generation run."""

    model: str
    prompt_version: str
    generated_at: str
    fallback_used: bool
    fallback_reason: Optional[str] = None


@dataclass(frozen=True)
class LinkRationale:
    """
    One CRE link's generated rationale -- meant to fill
    ``librarian.schemas.ProposedLink.rationale``, which every current
    Module C code path leaves ``None``.
    """

    cre_id: str
    rationale: str
    confidence: str
    fallback_used: bool
    trace: RationaleTrace


# ---------------------------------------------------------------------------
# LLM structured-output schema
# ---------------------------------------------------------------------------


class _RationalePayload(BaseModel):
    rationale: str = Field(min_length=1, max_length=REASON_MAX_LENGTH)


def rationale_response_json_schema() -> Dict[str, Any]:
    """Provider-friendly JSON schema for strict structured LLM outputs."""
    return _RationalePayload.model_json_schema()


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------


def _system_prompt() -> str:
    return (
        "You explain why an OWASP cheat sheet is a good match for a specific "
        "Common Requirement (CRE) entry. You will be given the cheat sheet's "
        "text, the CRE's id and text, and Module C's calibrated match score. "
        "Write ONE short, concrete sentence (max 60 words) grounded in the "
        "actual cheat sheet content and CRE text -- do not restate the score, "
        "do not invent facts not present in either text. "
        'Return ONLY valid JSON of the form {"rationale": "..."}.'
    )


def _user_payload(section_text: str, cre_id: str, cre_text: str, score: float) -> str:
    lines = [
        f"CHEATSHEET_TEXT: {section_text[:2000]}",
        "",
        f"CRE_ID: {cre_id}",
        f"CRE_TEXT: {(cre_text or '<no text available>')[:800]}",
        "",
        f"CALIBRATED_SCORE: {score:.3f}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default (production) LLM call -- lazy litellm import so this module stays
# import-light and hermetically testable without a real LLM dependency.
# ---------------------------------------------------------------------------


def _default_model_name() -> str:
    return os.environ.get(
        DEFAULT_MODEL_ENV_VAR,
        os.environ.get("CRE_LLM_CHAT_MODEL", DEFAULT_MODEL_FALLBACK),
    )


def default_llm_rationale_fn(
    system: str, user: str, *, model: str, timeout: Optional[float] = None
) -> Dict[str, Any]:
    """Production LLM call via LiteLLM. Raises on any failure; callers must
    handle fallback (this function intentionally does not swallow errors).

    ``timeout``, when given, is passed straight through to LiteLLM so the
    underlying HTTP request itself is bounded, letting the worker thread in
    ``_call_with_timeout`` actually terminate rather than just being
    abandoned.
    """
    try:
        import litellm  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without litellm
        raise RerankError(
            "litellm package is required for LLM rationale calls"
        ) from exc

    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=timeout,
    )
    choices = getattr(resp, "choices", None)
    if not choices:
        raise RerankError("LLM response contained no choices")
    content = choices[0].message.content
    if isinstance(content, list):  # some providers return content blocks
        content = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return json.loads(content)


def _call_with_timeout(
    fn: Callable[[], Dict[str, Any]], timeout_seconds: float
) -> Dict[str, Any]:
    """Run ``fn`` with a hard wall-clock timeout so a hung LLM call can never
    block the pipeline; raises on timeout or on any exception from ``fn``.

    Uses an explicit (non-context-manager) executor so a timeout returns to
    the caller immediately instead of blocking on ``shutdown(wait=True)``
    for a thread that is still running the (now-abandoned) call.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        pool.shutdown(wait=False)
        raise RerankError(
            f"LLM rationale call exceeded {timeout_seconds}s timeout"
        ) from exc
    except Exception:
        pool.shutdown(wait=False)
        raise
    else:
        pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# LangGraph flow: generate -> (success: format) | (failure: fallback -> format)
# ---------------------------------------------------------------------------


class _RationaleState(TypedDict, total=False):
    section_text: str
    cre_id: str
    cre_text: str
    score: float
    llm_rationale_fn: Callable[..., Dict[str, Any]]
    model_name: str
    timeout_seconds: float
    generated_at: str
    rationale_text: Optional[str]
    fallback_used: bool
    fallback_reason: Optional[str]
    result: LinkRationale


def _node_generate(state: _RationaleState) -> _RationaleState:
    """Call the LLM and validate its output. On any failure, record the
    reason and leave ``rationale_text`` unset; the conditional edge below
    routes to the fallback node instead of raising."""
    system = _system_prompt()
    user = _user_payload(
        state["section_text"], state["cre_id"], state["cre_text"], state["score"]
    )
    llm_rationale_fn = state["llm_rationale_fn"]
    model_name = state["model_name"]
    timeout_seconds = state["timeout_seconds"]

    try:
        raw = _call_with_timeout(
            lambda: llm_rationale_fn(system, user, model=model_name), timeout_seconds
        )
        payload = _RationalePayload.model_validate(raw)
    except (RerankError, ValidationError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("LLM rationale failed for %s: %s", state["cre_id"], exc)
        state["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:REASON_MAX_LENGTH]
        state["rationale_text"] = None
        return state
    except Exception as exc:  # defensive: never let an unexpected error crash the run
        logger.warning(
            "LLM rationale failed unexpectedly for %s: %s", state["cre_id"], exc
        )
        state["fallback_reason"] = f"unexpected:{type(exc).__name__}: {exc}"[
            :REASON_MAX_LENGTH
        ]
        state["rationale_text"] = None
        return state

    state["rationale_text"] = payload.rationale[:REASON_MAX_LENGTH]
    return state


def _route_after_generate(state: _RationaleState) -> str:
    return "format" if state.get("rationale_text") else "fallback"


def _node_fallback(state: _RationaleState) -> _RationaleState:
    """Deterministic, honest fallback: no LLM prose, just the score."""
    state["fallback_used"] = True
    state["rationale_text"] = (
        f"Retrieval/rerank score {state['score']:.2f}; LLM explanation unavailable."
    )
    return state


def _node_format(state: _RationaleState) -> _RationaleState:
    trace = RationaleTrace(
        model=state["model_name"],
        prompt_version=PROMPT_VERSION,
        generated_at=state["generated_at"],
        fallback_used=state.get("fallback_used", False),
        fallback_reason=(
            state.get("fallback_reason") if state.get("fallback_used") else None
        ),
    )
    state["result"] = LinkRationale(
        cre_id=state["cre_id"],
        rationale=state["rationale_text"],
        confidence=classify_confidence(state["score"]),
        fallback_used=state.get("fallback_used", False),
        trace=trace,
    )
    return state


def build_rationale_graph():
    """Compile and return the Workstream E LangGraph flow.

    Nodes: ``generate`` -> (``format`` | ``fallback`` -> ``format``) -> END.
    """
    from langgraph.graph import StateGraph, START, END

    graph = StateGraph(_RationaleState)
    graph.add_node("generate", _node_generate)
    graph.add_node("fallback", _node_fallback)
    graph.add_node("format", _node_format)

    graph.add_edge(START, "generate")
    graph.add_conditional_edges(
        "generate", _route_after_generate, {"format": "format", "fallback": "fallback"}
    )
    graph.add_edge("fallback", "format")
    graph.add_edge("format", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_link_rationale(
    section_text: str,
    cre_id: str,
    cre_text: str,
    score: float,
    *,
    llm_rationale_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    model_name: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> LinkRationale:
    """
    Generate a natural-language rationale for one CRE link, via the
    LangGraph flow above.

    Intended to fill ``librarian.schemas.ProposedLink.rationale`` for the
    single top-1 candidate Module C's ``decide()`` already chose -- this
    does not rerank or re-decide anything.

    ``llm_rationale_fn`` defaults to a LiteLLM-backed call
    (:func:`default_llm_rationale_fn`); tests and harnesses should inject a
    deterministic stub instead. Never raises on LLM failure -- falls back to
    a short, honest, score-only rationale and marks the trace accordingly.
    """
    if not isinstance(cre_id, str) or not cre_id.strip():
        raise RerankError(f"cre_id must be a non-empty string, got {cre_id!r}")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(
        timeout_seconds, bool
    ):
        raise RerankError(
            f"timeout_seconds must be a non-boolean number, got {timeout_seconds!r}"
        )
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise RerankError(
            f"timeout_seconds must be a finite number > 0, got {timeout_seconds!r}"
        )
    # classify_confidence performs the score range/type validation; reuse it
    # up front so a bad score fails fast, before any LLM call is attempted.
    classify_confidence(score)

    resolved_model = model_name or _default_model_name()
    if llm_rationale_fn is not None:
        score_fn = llm_rationale_fn
    else:
        # Bind the request-level timeout only for the built-in LiteLLM path;
        # injected stubs are not required to accept a ``timeout`` kwarg.
        score_fn = partial(default_llm_rationale_fn, timeout=timeout_seconds)

    app = build_rationale_graph()
    result = app.invoke(
        {
            "section_text": section_text,
            "cre_id": cre_id,
            "cre_text": cre_text,
            "score": float(score),
            "llm_rationale_fn": score_fn,
            "model_name": resolved_model,
            "timeout_seconds": timeout_seconds,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": False,
            "fallback_reason": None,
        }
    )
    return result["result"]
