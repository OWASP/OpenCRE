"""Answer a question from retrieved comprehension documents, with citations."""

from __future__ import annotations

import re
from typing import Callable, List, Sequence, Tuple

LlmFn = Callable[[str, str], str]

SYSTEM = (
    "Answer the question using ONLY the numbered sources. Be precise about what is "
    "counted and where (e.g. per practice vs overall). If the sources do not contain "
    "the answer, reply exactly: UNKNOWN. Otherwise answer in 1-4 sentences and end "
    "with the source numbers you used like [1][3]. Never add facts not in the sources. "
    "If the question assumes something the sources contradict, say the premise is incorrect and give the correct fact. "
    "If sources describe different versions, answer for the latest version and name it. "
    "Answer only about the project/standard the question names; sources about a different project do not count."
)


def synthesize(
    question: str, hits: Sequence[Tuple[str, List[str]]], llm: LlmFn
) -> Tuple[str, List[str]]:
    """``hits`` = (text, citations). Returns (answer, citations used); ("", []) if unknown."""
    numbered = "\n\n".join(
        f"[{i + 1}] {t.split(chr(10) + chr(10) + 'Citations:')[0]}"
        for i, (t, _) in enumerate(hits)
    )
    out = (llm(SYSTEM, f"Question: {question}\n\nSources:\n{numbered}") or "").strip()
    if not out or out.upper().startswith("UNKNOWN"):
        return "", []
    used = sorted(
        {int(n) for n in re.findall(r"\[(\d+)\]", out) if 0 < int(n) <= len(hits)}
    )
    cites: List[str] = []
    for i in used:
        for c in hits[i - 1][1]:
            if c not in cites:
                cites.append(c)
    return out, cites
