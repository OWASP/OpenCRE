"""Feature flags for answer-quality techniques (off by default, except those in DEFAULT_ON).

Each flag is an env var ``OWASP_CX_<NAME>`` set to 1/true/on (0/false/no/off turns a default-on flag off). Flags can be
combined freely; ``scripts``/eval toggles them for ablation.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

NAMES = (
    "EXPAND",  # neighbouring chunks around each raw hit
    "RERANK",  # LLM rerank of a wide candidate pool
    "QUERY",  # query understanding: clean, decompose, clarify
    "VERIFY",  # check the answer against its sources
    "PERPROJECT",  # per-project retrieval for multi-project questions
    "COUNT",  # enumerate-then-count for "how many" questions
    "MERGED",  # one call: clean question + pick sources + answer + self-check
    "CACHE",  # in-process answer cache (real traffic, not evals)
    "LONGCTX",  # questions naming 1-3 projects: read the whole project text, not snippets
    "FAST",  # final-answer model runs with thinking off (latency)
    "PROJROUTE",  # no project named: pick one by similarity to project overviews
    "COMPLETE",  # answer every part and every named standard; include all stated items
    "PERSTD",  # questions naming 2-3 projects: read each whole, answer each standard separately
    "PICK",  # no project named: a cheap model picks it from the best-matching projects (or says unsure)
    "COMPLETE2",  # second pass: a cheap checker finds unanswered parts, the reader answers them
    "NEG",  # negation questions (NOT / except): test every option against the sources before choosing
    "PREFIXCACHE",  # sources first, question last, so the provider can reuse the cached project text
    "WIDEMATCH",  # whole-project reading can match any repo with raw chunks, not only digested ones
    "EDITION",  # answer for the edition/year/version the question names; never mix editions
    "ROUTE",  # people/count questions: whole-project read with a stronger reader model
    "TOPPROJECTS",  # no project named: the 3 best-matching projects each contribute sources
    "DECOMPOSE",  # multi-part questions: answer each part separately, then combine
    # RAG/OIE framework-native cutover
    "LI_RETRIEVE",  # public QueryFusionRetriever RRF (num_queries=1) over dense lists
    "LI_VSTORE",  # VectorStoreIndex over OpenCRE pgvector (read-only; no second SoT)
    "LC_ROUTER",  # LangChain tool-calling intent router (owasp_agent)
    "CITATIONS",  # strip uncited sentences after synthesize
    "MODERN_RERANK",  # Cohere/LI modern rerank (prefer over/beside LLM RERANK)
)

# Alias CRE_RAG_PARITY_* → OWASP_CX_* so staging can flip either name.
# Ask-side keyword/FTS HYBRID (and CRE_RAG_PARITY_LI_HYBRID) was removed — dense
# + LI QueryFusion/VectorStoreIndex is the retrieve path.
_PARITY_ALIASES = {
    "LI_RETRIEVE": ("CRE_RAG_PARITY_LI_RETRIEVE",),
    "LI_VSTORE": ("CRE_RAG_PARITY_LI_VSTORE",),
    "LC_ROUTER": ("CRE_RAG_PARITY_LC_ROUTER",),
    "CITATIONS": ("CRE_RAG_PARITY_CITATIONS",),
    "MODERN_RERANK": ("CRE_RAG_PARITY_MODERN_RERANK",),
}


# TOPPROJECTS: proven on 246-Q clean set. LI_VSTORE+LI_RETRIEVE: accepted on staging
# ablates (TASK-14.1/14.2); rollback = git revert (TASK-14.8). CITATIONS: strip
# uncited sentences (TASK-14.10). Force off with =0.
DEFAULT_ON = frozenset({"TOPPROJECTS", "LI_RETRIEVE", "LI_VSTORE", "CITATIONS"})


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def on(name: str) -> bool:
    v = (os.environ.get(f"OWASP_CX_{name}", "") or "").strip()
    if v:
        return _truthy(v)
    for alias in _PARITY_ALIASES.get(name, ()):
        av = (os.environ.get(alias, "") or "").strip()
        if av:
            return _truthy(av)
    return name in DEFAULT_ON


def active() -> list:
    return [n for n in NAMES if on(n)]


_HELPER: Optional[Callable[[str, str], str]] = None


def helper_llm() -> Optional[Callable[[str, str], str]]:
    """Cheap deterministic model for rerank/query/verify calls (system, user) -> text."""
    global _HELPER
    if _HELPER is None:
        try:
            from application.prompt_client import litellm_router

            _HELPER = litellm_router.system_user_fn(
                os.environ.get("OWASP_CX_HELPER_MODEL", "gemini/gemini-2.5-flash-lite"),
                temperature=0.0,
                extra_try_kwargs={"reasoning_effort": "disable"},
            )
        except Exception:
            return None
    return _HELPER
