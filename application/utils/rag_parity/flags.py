"""Feature flags for RAG/OIE parity phases (staging-oriented; prod defaults off)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RagParityFlags:
    """Staging defaults documented; production must keep decide-critical paths off."""

    # Phase 2
    ingest_pipeline: bool = False
    use_docling: bool = False
    # Phase 3 (keyword/FTS LI_HYBRID removed — use LI_RETRIEVE / multi-query)
    lc_router: bool = False
    citation_synthesizer: bool = False
    # Phase 4
    modern_rerank: bool = False
    contextual_compression: bool = False
    # Phase 5
    knowledge_claim_extract: bool = False
    # Phase 6
    langfuse: bool = False
    otel: bool = False
    # Phase 7
    redis_answer_cache: bool = False
    queue_row_lock_default: bool = True  # refuse silent degrade on Postgres
    langgraph_checkpointer: bool = False


def _any_env_bool(*names: str, default: bool = False) -> bool:
    """True if any named env is truthy; False if any is explicitly off; else default."""
    saw = False
    for name in names:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            continue
        saw = True
        if _env_bool(name, False):
            return True
    if saw:
        return False
    return default


def load_flags() -> RagParityFlags:
    # Prefer CRE_RAG_PARITY_*; also honor OWASP_CX_* ask aliases (TASK-14.11).
    return RagParityFlags(
        ingest_pipeline=_env_bool("CRE_RAG_PARITY_INGEST", False),
        use_docling=_env_bool("CRE_RAG_PARITY_DOCLING", False),
        lc_router=_any_env_bool(
            "CRE_RAG_PARITY_LC_ROUTER", "OWASP_CX_LC_ROUTER", default=False
        ),
        citation_synthesizer=_any_env_bool(
            "CRE_RAG_PARITY_CITATIONS", "OWASP_CX_CITATIONS", default=False
        ),
        modern_rerank=_any_env_bool(
            "CRE_RAG_PARITY_MODERN_RERANK", "OWASP_CX_MODERN_RERANK", default=False
        ),
        contextual_compression=_env_bool("CRE_RAG_PARITY_COMPRESSION", False),
        knowledge_claim_extract=_env_bool("CRE_RAG_PARITY_CLAIMS", False),
        langfuse=_env_bool("CRE_RAG_PARITY_LANGFUSE", False),
        otel=_env_bool("CRE_RAG_PARITY_OTEL", False),
        redis_answer_cache=_env_bool("CRE_RAG_PARITY_REDIS_ANSWER_CACHE", False),
        queue_row_lock_default=_env_bool("CRE_RAG_PARITY_QUEUE_ROW_LOCK", True),
        langgraph_checkpointer=_env_bool("CRE_RAG_PARITY_LANGGRAPH_CHECKPOINT", False),
    )
