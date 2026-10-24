"""Answer a question from retrieved comprehension documents, with citations."""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Callable, List, Sequence, Tuple

LlmFn = Callable[[str, str], str]

# Evidence behind the answer being built on this thread/context (callers that want to
# show their work, e.g. MCP ``ask``, read it right after answering).
_EVIDENCE: "ContextVar[list]" = ContextVar("comprehension_evidence", default=[])


# The chat's earlier turns for the question being answered. The answer call sends them as real
# user/assistant messages (native multi-turn), so the model reads them as background, not as questions.
_HISTORY: "ContextVar[list]" = ContextVar("comprehension_history", default=[])
HISTORY_RULE = (
    " Earlier messages in this conversation are background only: answer ONLY the final question, "
    "do not answer the earlier questions again."
)
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 600


def set_history(history) -> None:
    """Prepare the earlier chat turns (last few, trimmed, alternating roles) for the answer call."""
    from application.utils.chat_history import normalize_chat_messages

    turns = []
    for m in normalize_chat_messages(history)[-MAX_HISTORY_TURNS:]:
        content = m["content"][:MAX_HISTORY_CHARS]
        if turns and turns[-1]["role"] == m["role"]:
            turns[-1]["content"] += "\n" + content  # providers want alternating roles
        else:
            turns.append({"role": m["role"], "content": content})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    _HISTORY.set(turns)


def get_history() -> list:
    return list(_HISTORY.get())


def with_history(messages: list) -> list:
    """[system, ...earlier turns, final user message]: native multi-turn for the answer call."""
    turns = get_history()
    if not turns or len(messages) < 2:
        return list(messages)
    return [messages[0], *turns, *messages[1:]]


def reset_evidence() -> None:
    _EVIDENCE.set([])


def take_evidence() -> list:
    return list(_EVIDENCE.get())


def _record_evidence(
    hits: Sequence[Tuple[str, List[str]]], used: Sequence[int]
) -> None:
    from application.utils.comprehension.toolkit import body_of, path_of

    items = list(_EVIDENCE.get())
    for i in used:
        text, cites = hits[i - 1]
        body = body_of(text)
        snippet = body.split(": ", 1)[-1] if path_of(body) else body
        items.append(
            {
                "n": i,
                "path": path_of(body),
                "snippet": snippet.strip()[:500],
                "citations": list(cites)[:3],
            }
        )
    _EVIDENCE.set(items)


SYSTEM = (
    "Answer the question using ONLY the numbered sources. Be precise about what is "
    "counted and where (e.g. per practice vs overall). If the sources do not state what "
    "is asked, reply exactly: UNKNOWN. If they state only part of it, give that part and say "
    "plainly what they do not state. Otherwise answer in 1-4 sentences and end "
    "with the source numbers you used like [1][3]. Never add facts not in the sources. "
    "If the question assumes something the sources contradict, say the premise is incorrect and give the correct fact. "
    "If sources describe different versions, answer for the latest version and name it. "
    "Answer only about the project/standard the question names; sources about a different project do not count."
)


COUNT_SYSTEM = SYSTEM + (
    " For a how-many question: first list each distinct matching item the sources name, one per "
    "line with its source number, then state the total on a final line. If a source states the "
    "total, use it and mention any disagreement with the list."
)


EDITION_RULE = (
    " Sources often cover several editions (years, versions, translations). If the question names "
    "an edition, use only sources for that edition and say which one you used. If it names none, "
    "use the latest edition and name it. Never combine people, dates or facts from different "
    "editions in one answer; when asked about credits (leaders, authors, reviewers, translators), "
    "list only those the sources tie to the edition asked about."
)


COMPLETE_RULE = (
    " Cover every part of the question: if it has several parts or names several standards or "
    "projects, answer each one in turn (one short line per part), and when asked to list or compare, "
    "include every item the sources state. For a 'which is NOT ...' question, check each option "
    "against the sources before choosing."
)


PERSTD_RULE = (
    " The question concerns several standards or projects. Answer for each one separately, naming it "
    "(one short paragraph each), using only the sources about that project, then add a brief "
    "combined conclusion. If the sources do not cover one of them, say so for that one."
)


NEG_RE = re.compile(
    r"\bnot\b|n't\b|\bexcept\b|\bexcluding\b|\bnone of\b|\bnever\b|\bwithout\b", re.I
)
NEG_RULE = (
    " The question asks what is NOT / EXCEPT / excluded. First list every candidate option the question "
    "or the sources give, then test each one against the sources (stated: yes/no), and only then name the "
    "option(s) the sources do not support. Do not answer from the first sentence you find."
)


def synthesize(
    question: str,
    hits: Sequence[Tuple[str, List[str]]],
    llm: LlmFn,
    *,
    system: str = SYSTEM,
) -> Tuple[str, List[str]]:
    """``hits`` = (text, citations). Returns (answer, citations used); ("", []) if unknown."""
    from application.utils.comprehension import flags

    if get_history():
        system += HISTORY_RULE
    if flags.on("EDITION"):
        system += EDITION_RULE
    if flags.on("COMPLETE"):
        system += COMPLETE_RULE
    numbered = "\n\n".join(
        f"[{i + 1}] {t.split(chr(10) + chr(10) + 'Citations:')[0]}"
        for i, (t, _) in enumerate(hits)
    )
    if flags.on("PREFIXCACHE"):
        # Same project text first: providers cache the longest shared prefix across questions.
        user = f"Sources:\n{numbered}\n\nQuestion: {question}"
    else:
        user = f"Question: {question}\n\nSources:\n{numbered}"
    out = (llm(system, user) or "").strip()
    if not out or out.upper().startswith("UNKNOWN"):
        return "", []
    used = sorted(
        {int(n) for n in re.findall(r"\[(\d+)\]", out) if 0 < int(n) <= len(hits)}
    )
    _record_evidence(hits, used)
    cites: List[str] = []
    for i in used:
        for c in hits[i - 1][1]:
            if c not in cites:
                cites.append(c)
    return out, cites
