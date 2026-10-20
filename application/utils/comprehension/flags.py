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
    "LONGCTX",  # one-project questions: read the whole project text, not snippets
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
