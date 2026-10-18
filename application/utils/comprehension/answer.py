"""Router hook: answer from comprehension documents among the top candidates."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Optional, Sequence, Tuple, List

from application.utils.comprehension.store import SLUG_PREFIX
from application.utils.comprehension.synthesize import synthesize

CompletionFn = Callable[[Sequence[dict]], str]
_MAX_SOURCES = 10


def enabled() -> bool:
    return (
        os.environ.get("OWASP_COMPREHENSION_ENABLED", "1") or "1"
    ).strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def abstain_enabled() -> bool:
    return (
        os.environ.get("OWASP_COMPREHENSION_ABSTAIN", "1") or "1"
    ).strip().lower() not in ("0", "false", "no", "off")


ABSTAIN_MESSAGE = (
    "I couldn't find that in the indexed OWASP sources, so I won't guess. "
    "Try naming the project or standard, or rephrase the question."
)


# Questions the CRE lane answers (mappings, OpenCRE itself, what's new): never hard-abstain on these.
_CRE_STYLE = re.compile(
    r"\b(map|mapping|maps|opencre|cre|mcp|what'?s new|what is new|compare|cheat ?sheet)\b",
    re.I,
)


def should_abstain(question: str) -> bool:
    return abstain_enabled() and not _CRE_STYLE.search(question or "")


_PLAN: dict = {}


def _plan(question: str) -> dict:
    """Query-understanding result for a question (cached; {} when the flag is off)."""
    from application.utils.comprehension import flags
    from application.utils.comprehension.extras import understand_query

    if not flags.on("QUERY"):
        return {}
    if question not in _PLAN:
        llm = flags.helper_llm()
        try:
            _PLAN[question] = understand_query(question, llm) if llm else {}
        except Exception:
            _PLAN[question] = {}
        if len(_PLAN) > 256:
            _PLAN.pop(next(iter(_PLAN)))
    return _PLAN[question]


def clarification_for(question: str) -> str:
    """A clarifying question to return instead of an answer ('' when none)."""
    return str(_plan(question).get("clarify") or "")


def merge_with_dedicated(question: str, cands: Sequence[Any]) -> List[Any]:
    """cands plus directly retrieved comprehension docs (deduped, best first)."""
    if not enabled():
        return list(cands)
    from application.utils.comprehension import flags
    from application.utils.comprehension.extras import rerank_order
    from application.utils.comprehension.retrieve import fetch_comprehension_hits

    plan = _plan(question)
    clean = plan.get("query") or question
    extra_q = list(plan.get("parts") or [])
    seen = {getattr(c, "url", "") for c in cands}
    fetched = fetch_comprehension_hits(clean, extra_q)
    extra = [h for h in fetched if h.url not in seen]
    merged = list(cands) + extra
    merged.sort(key=lambda h: -float(getattr(h, "score", 0.0) or 0.0))
    if flags.on("RERANK"):
        comp = [h for h in merged if is_comprehension_hit(h)]
        llm = flags.helper_llm()
        if llm and len(comp) > 3:
            pool = comp[:30]
            order = rerank_order(
                clean, [_split_citations(h.content)[0] for h in pool], llm
            )
            if order:
                top = [pool[i] for i in order]
                rest = [h for h in merged if h not in top]
                merged = top + rest
                for rank, h in enumerate(top):
                    h.score = max(float(h.score or 0.0), 2.0 - 0.01 * rank)
    return merged


def is_comprehension_hit(hit: Any) -> bool:
    return f"/evidence/{SLUG_PREFIX}" in (getattr(hit, "url", "") or "")


def _split_citations(content: str) -> Tuple[str, List[str]]:
    body, _, tail = (content or "").partition("\n\nCitations:")
    return body.strip(), [
        c.strip() for c in tail.split(",") if c.strip().startswith("http")
    ]


def answer_from_candidates(
    question: str, cands: Sequence[Any], complete: Optional[CompletionFn]
) -> Optional[Tuple[str, List[str]]]:
    """Return (answer, citations) or None when no comprehension doc answers it."""
    if not enabled() or complete is None:
        return None
    hits = [c for c in cands if is_comprehension_hit(c)]
    # Overviews first: they state structure; claims/summaries add detail.
    from application.utils.comprehension import flags

    if not flags.on("RERANK"):
        hits.sort(
            key=lambda h: (
                0 if (getattr(h, "url", "") or "").endswith("-overview") else 1
            )
        )
    hits = hits[:_MAX_SOURCES]
    if not hits:
        return None
    sources = []
    for h in hits:
        body, cites = _split_citations(getattr(h, "content", ""))
        sources.append((body, cites))

    def llm(system: str, user: str) -> str:
        return complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )

    from application.utils.comprehension import extras
    from application.utils.comprehension.synthesize import COUNT_SYSTEM, SYSTEM

    plan = _plan(question)
    ask = plan.get("query") or question
    if plan.get("parts"):
        ask = f"{ask}\n(Answer each part: " + " | ".join(plan["parts"]) + ")"
    count_mode = flags.on("COUNT") and bool(extras.COUNT_RE.search(ask))
    answer, cites = synthesize(
        ask, sources, llm, system=COUNT_SYSTEM if count_mode else SYSTEM
    )
    if answer and flags.on("VERIFY"):
        hl = flags.helper_llm()
        if hl:
            numbered = "\n\n".join(f"[{i + 1}] {t}" for i, (t, _) in enumerate(sources))
            try:
                _, answer = extras.verify_answer(ask, answer, numbered, hl)
            except Exception:
                pass
    return (answer, cites) if answer else None
