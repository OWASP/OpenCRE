"""Feature flags for answer-quality techniques (all off by default).

Each flag is an env var ``OWASP_CX_<NAME>`` set to 1/true/on. Flags can be
combined freely; ``scripts``/eval toggles them for ablation.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

NAMES = (
    "EXPAND",  # neighbouring chunks around each raw hit
    "HYBRID",  # keyword (full-text) search fused with vectors
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
    "DECOMPOSE",  # multi-part questions: answer each part separately, then combine
)


def on(name: str) -> bool:
    v = (os.environ.get(f"OWASP_CX_{name}", "") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


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
