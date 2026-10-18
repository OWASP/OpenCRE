"""Router hook: answer from comprehension documents among the top candidates."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional, Sequence, Tuple, List

from application.utils.comprehension.store import SLUG_PREFIX
from application.utils.comprehension.synthesize import synthesize

CompletionFn = Callable[[Sequence[dict]], str]
_MAX_SOURCES = 8


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
    return (os.environ.get("OWASP_COMPREHENSION_ABSTAIN", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


ABSTAIN_MESSAGE = (
    "I couldn't find that in the indexed OWASP sources, so I won't guess. "
    "Try naming the project or standard, or rephrase the question."
)


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
    hits.sort(
        key=lambda h: 0 if (getattr(h, "url", "") or "").endswith("-overview") else 1
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

    answer, cites = synthesize(question, sources, llm)
    return (answer, cites) if answer else None
