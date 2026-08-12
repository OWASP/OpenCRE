"""
RFC Workstream E — LLM Re-Rank and Decision Graph (LangGraph).

See: docs/rfc/cheatsheets-llm-autonomous-mapping-rfc.md, section 5
("Workstream E: LLM Re-Rank and Decision Graph (LangGraph)") and the
Issue E checklist in section 12.

This module owns the "ReRank/Explain -> Threshold" stage of the overall
pipeline (docs/rfc section 7): given a ``CheatsheetRecord`` (Workstream B,
``application/defs/cheatsheet_defs.py``) and the top-k ``CandidateCRE``
shortlist for it (Workstream D, ``retrieve_candidate_cres``), it asks an LLM
to re-rank and justify the shortlist, assigns a confidence band to each
result, and always returns a usable ``RankedCRE`` list — even when the LLM
call fails, times out, or returns malformed output — by falling back to the
retrieval-only ordering.

Design notes
------------
* ``CandidateCRE`` is defined *here* rather than imported from Workstream D
  because that workstream's ``retrieve_candidate_cres`` has not landed yet.
  The field set (``cre_id``, ``score``, ``text``) mirrors the RFC's
  ``CandidateCRE`` contract exactly, so swapping in the real Workstream D
  output only requires constructing this same dataclass.
* The LLM call is dependency-injected as ``llm_score_fn`` — a plain
  ``(system, user) -> dict`` callable — exactly like the ``ai_client`` seam
  in ``application/prompt_client/embed_alignment.py`` and the ``score_fn``
  seam in ``application/utils/librarian/cross_encoder.py``. Production code
  never has to inject anything (a LiteLLM-backed default is wired lazily so
  this module stays import-light for tests); the test suite and any
  harness inject a deterministic stub instead, which keeps the LangGraph
  flow hermetically testable.
* Confidence bands and thresholds follow the RFC's bootstrap defaults
  (section 11 "Open Questions"): high >= 0.85, medium >= 0.70, else low.
  Both are overridable via environment variables so they can be
  recalibrated later against PR #865-derived precision/recall data without
  a code change.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field, ValidationError

from application.defs.cheatsheet_defs import CheatsheetRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confidence thresholds (RFC section 11 bootstrap defaults; recalibrate via env)
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE_THRESHOLD = float(
    os.environ.get("CRE_CHEATSHEET_RERANK_HIGH_THRESHOLD", "0.85")
)
MEDIUM_CONFIDENCE_THRESHOLD = float(
    os.environ.get("CRE_CHEATSHEET_RERANK_MEDIUM_THRESHOLD", "0.70")
)

# Identifiers persisted into RerankTrace for the RFC audit trail (mirrors
# RETRIEVER_NAME / RERANKER_NAME conventions used elsewhere in the codebase).
RERANKER_NAME = "llm-cheatsheet-reranker"
PROMPT_VERSION = "v1"

DEFAULT_TOP_N = 5
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MODEL_ENV_VAR = "CRE_CHEATSHEET_RERANK_MODEL"
DEFAULT_MODEL_FALLBACK = "gemini/gemini-2.5-flash"

REASON_MAX_LENGTH = 400


class RerankError(ValueError):
    """Base class for reranker construction/usage failures."""


def classify_confidence(score: float) -> str:
    """
    Map a 0-1 re-rank score to a confidence band ("high" | "medium" | "low").

    Thresholds are the RFC's bootstrap defaults and are recalibratable via
    ``CRE_CHEATSHEET_RERANK_HIGH_THRESHOLD`` / ``_MEDIUM_THRESHOLD``.
    """
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise RerankError(f"score must be a number, got {score!r}")
    if not (0.0 <= float(score) <= 1.0):
        raise RerankError(f"score must be in [0, 1], got {score!r}")

    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateCRE:
    """
    One retrieval-stage candidate for a CheatsheetRecord.

    Mirrors the RFC's Workstream D output contract. ``text`` is optional
    context (e.g. the CRE's embeddings_content) given to the LLM so it can
    judge fit; when absent the LLM is told only the cre_id, which degrades
    rationale quality but never breaks the flow.
    """

    cre_id: str
    score: float
    text: str = ""


@dataclass(frozen=True)
class RerankTrace:
    """Audit metadata captured for every rerank run (RFC Issue E, criterion 3)."""

    model: str
    prompt_version: str
    generated_at: str
    fallback_used: bool
    fallback_reason: Optional[str] = None


@dataclass(frozen=True)
class RankedCRE:
    """One re-ranked, explained candidate — Workstream E's output contract."""

    cre_id: str
    score: float
    retrieval_score: float
    confidence: str
    reason: str
    needs_review: bool
    trace: RerankTrace


# ---------------------------------------------------------------------------
# LLM structured-output schema (strict; mirrors embed_alignment.AlignmentPayload)
# ---------------------------------------------------------------------------


class _RerankItem(BaseModel):
    cre_id: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class _RerankPayload(BaseModel):
    ranked: List[_RerankItem]


def rerank_response_json_schema() -> Dict[str, Any]:
    """Provider-friendly JSON schema for strict structured LLM outputs."""
    return _RerankPayload.model_json_schema()


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------


def _system_prompt() -> str:
    return (
        "You map an OWASP cheat sheet to the Common Requirement (CRE) entries "
        "it best satisfies. You will be given the cheat sheet's title, summary, "
        "and headings, plus a shortlist of candidate CREs with their ids. "
        "Score how well each candidate CRE matches the cheat sheet's content on "
        "a 0.0-1.0 scale (1.0 = the cheat sheet is clearly authoritative "
        "guidance for that CRE), and give a short one-sentence reason for each "
        "score, grounded in the cheat sheet's actual headings/summary. "
        "Only score cre_ids given to you; never invent new ones. "
        "Return ONLY valid JSON of the form "
        '{"ranked": [{"cre_id": "...", "score": 0.0, "reason": "..."}]}, '
        "one entry per candidate given."
    )


def _user_payload(record: CheatsheetRecord, candidates: List[CandidateCRE]) -> str:
    lines = [
        f"CHEATSHEET_TITLE: {record.title}",
        f"CHEATSHEET_SUMMARY: {record.summary}",
        "CHEATSHEET_HEADINGS: " + "; ".join(record.headings),
        "",
        "CANDIDATE_CRES (cre_id | text):",
    ]
    for c in candidates:
        text_preview = (c.text or "<no text available>")[:800]
        lines.append(f"{c.cre_id} | {text_preview}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default (production) LLM call — lazy litellm import so this module stays
# import-light and hermetically testable without a real LLM dependency.
# ---------------------------------------------------------------------------


def _default_model_name() -> str:
    return os.environ.get(
        DEFAULT_MODEL_ENV_VAR,
        os.environ.get("CRE_LLM_CHAT_MODEL", DEFAULT_MODEL_FALLBACK),
    )


def default_llm_score_fn(system: str, user: str, *, model: str) -> Dict[str, Any]:
    """Production LLM call via LiteLLM. Raises on any failure; callers must
    handle fallback (this function intentionally does not swallow errors)."""
    try:
        import litellm  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without litellm
        raise RerankError("litellm package is required for LLM re-rank calls") from exc

    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
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
    block the pipeline; raises on timeout or on any exception from ``fn``."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise RerankError(
                f"LLM re-rank call exceeded {timeout_seconds}s timeout"
            ) from exc


# ---------------------------------------------------------------------------
# LangGraph flow: rerank -> (success: classify) | (failure: fallback -> classify)
# ---------------------------------------------------------------------------


class _RerankState(TypedDict, total=False):
    record: CheatsheetRecord
    candidates: List[CandidateCRE]
    top_n: int
    llm_score_fn: Callable[..., Dict[str, Any]]
    model_name: str
    timeout_seconds: float
    generated_at: str
    scored: Dict[str, Dict[str, Any]]  # cre_id -> {"score": float, "reason": str}
    fallback_used: bool
    fallback_reason: Optional[str]
    ranked: List[RankedCRE]


def _node_llm_rerank(state: _RerankState) -> _RerankState:
    """Call the LLM, validate its output, and record per-candidate scores.

    On any failure (LLM error, timeout, malformed JSON, schema violation)
    this node records the reason and leaves ``scored`` empty; the
    conditional edge below routes to the fallback node instead of raising.
    """
    record = state["record"]
    candidates = state["candidates"]
    llm_score_fn = state["llm_score_fn"]
    model_name = state["model_name"]
    timeout_seconds = state["timeout_seconds"]

    system = _system_prompt()
    user = _user_payload(record, candidates)

    try:
        raw = _call_with_timeout(
            lambda: llm_score_fn(system, user, model=model_name), timeout_seconds
        )
        payload = _RerankPayload.model_validate(raw)
    except (RerankError, ValidationError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("LLM re-rank failed for %s: %s", record.source_id, exc)
        state["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:REASON_MAX_LENGTH]
        state["scored"] = {}
        return state
    except Exception as exc:  # defensive: never let an unexpected error crash the run
        logger.warning(
            "LLM re-rank failed unexpectedly for %s: %s", record.source_id, exc
        )
        state["fallback_reason"] = f"unexpected:{type(exc).__name__}: {exc}"[
            :REASON_MAX_LENGTH
        ]
        state["scored"] = {}
        return state

    known_ids = {c.cre_id for c in candidates}
    scored: Dict[str, Dict[str, Any]] = {}
    for item in payload.ranked:
        if item.cre_id not in known_ids:
            logger.info(
                "Dropping hallucinated cre_id %r not in candidate shortlist for %s",
                item.cre_id,
                record.source_id,
            )
            continue
        scored[item.cre_id] = {
            "score": item.score,
            "reason": item.reason[:REASON_MAX_LENGTH],
        }

    if not scored:
        state["fallback_reason"] = "LLM returned no valid scored candidates"

    state["scored"] = scored
    return state


def _route_after_rerank(state: _RerankState) -> str:
    return "classify" if state.get("scored") else "fallback"


def _node_fallback(state: _RerankState) -> _RerankState:
    """Retrieval-only scoring: use each candidate's raw similarity as-is."""
    state["fallback_used"] = True
    state["scored"] = {
        c.cre_id: {
            "score": max(0.0, min(1.0, c.score)),
            "reason": "Retrieval-only score (LLM re-rank unavailable).",
        }
        for c in state["candidates"]
    }
    return state


def _node_classify(state: _RerankState) -> _RerankState:
    candidates = state["candidates"]
    scored = state["scored"]
    fallback_used = state.get("fallback_used", False)
    fallback_reason = state.get("fallback_reason")
    trace = RerankTrace(
        model=state["model_name"],
        prompt_version=PROMPT_VERSION,
        generated_at=state["generated_at"],
        fallback_used=fallback_used,
        fallback_reason=fallback_reason if fallback_used else None,
    )

    ranked: List[RankedCRE] = []
    for c in candidates:
        entry = scored.get(c.cre_id)
        if entry is None:
            # LLM succeeded overall but skipped this one candidate: fall back
            # to its retrieval score individually rather than dropping it.
            entry = {
                "score": max(0.0, min(1.0, c.score)),
                "reason": "Not scored by reranker; using retrieval score.",
            }
        confidence = classify_confidence(entry["score"])
        ranked.append(
            RankedCRE(
                cre_id=c.cre_id,
                score=entry["score"],
                retrieval_score=c.score,
                confidence=confidence,
                reason=entry["reason"],
                needs_review=(confidence == "low") or fallback_used,
                trace=trace,
            )
        )

    ranked.sort(key=lambda r: r.score, reverse=True)
    state["ranked"] = ranked[: state["top_n"]]
    return state


def build_rerank_graph():
    """Compile and return the Workstream E LangGraph flow.

    Nodes: ``rerank`` -> (``classify`` | ``fallback`` -> ``classify``) -> END.
    Exposed standalone so it can be inspected, visualized, or exercised
    directly in integration tests without going through the convenience
    wrapper below.
    """
    from langgraph.graph import StateGraph, END

    graph = StateGraph(_RerankState)
    graph.add_node("rerank", _node_llm_rerank)
    graph.add_node("fallback", _node_fallback)
    graph.add_node("classify", _node_classify)

    graph.set_entry_point("rerank")
    graph.add_conditional_edges(
        "rerank", _route_after_rerank, {"classify": "classify", "fallback": "fallback"}
    )
    graph.add_edge("fallback", "classify")
    graph.add_edge("classify", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entrypoint (RFC function-level API, section 6)
# ---------------------------------------------------------------------------


def rerank_candidates_with_llm(
    record: CheatsheetRecord,
    candidates: List[CandidateCRE],
    *,
    llm_score_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    top_n: int = DEFAULT_TOP_N,
    model_name: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> List[RankedCRE]:
    """
    Re-rank ``candidates`` for ``record`` via the LangGraph flow above.

    ``llm_score_fn`` defaults to a LiteLLM-backed call
    (:func:`default_llm_score_fn`); tests and harnesses should inject a
    deterministic stub instead. Never raises on LLM failure — falls back to
    retrieval-only ordering and marks the trace accordingly.
    """
    if not candidates:
        return []
    if top_n <= 0:
        raise RerankError(f"top_n must be > 0, got {top_n}")

    resolved_model = model_name or _default_model_name()
    score_fn = llm_score_fn or default_llm_score_fn

    app = build_rerank_graph()
    result = app.invoke(
        {
            "record": record,
            "candidates": candidates,
            "top_n": top_n,
            "llm_score_fn": score_fn,
            "model_name": resolved_model,
            "timeout_seconds": timeout_seconds,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": False,
            "fallback_reason": None,
        }
    )
    return result["ranked"]
