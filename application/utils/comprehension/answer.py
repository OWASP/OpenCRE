"""Router hook: answer from comprehension documents among the top candidates."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Optional, Sequence, Tuple, List

from application.utils.comprehension.store import SLUG_PREFIX
from application.utils.comprehension.synthesize import synthesize

CompletionFn = Callable[[Sequence[dict]], str]
_MAX_SOURCES = 10


def max_sources() -> int:
    try:
        return max(1, int(os.environ.get("OWASP_COMPREHENSION_SOURCES", _MAX_SOURCES)))
    except ValueError:
        return _MAX_SOURCES


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


def closest_projects(hits: Sequence[Any], limit: int = 3) -> List[str]:
    """Readable names of the projects behind the best comprehension hits (best first)."""
    from application.utils.comprehension.retrieve import _SLUG_RE, alias_phrase

    out: List[str] = []
    for h in hits:
        m = _SLUG_RE.match(getattr(h, "url", "") or "")
        if not m:
            continue
        name = alias_phrase(m.group(1)).title()
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def abstain_message(hits: Sequence[Any], question: str = "") -> str:
    """The not-found message, asking which project is meant when the closest matches are known.

    When the question already names one of them, asking "which project?" is wrong: plain not-found.
    """
    near = closest_projects(hits)
    if not near:
        return ABSTAIN_MESSAGE
    q = " " + re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip() + " "
    if any(f" {re.sub(r'[^a-z0-9]+', ' ', n.lower()).strip()} " in q for n in near):
        return ABSTAIN_MESSAGE
    return (
        "I couldn't find that in the indexed OWASP sources, so I won't guess. "
        f"Which project or standard do you mean? Closest matches: {', '.join(near)}."
    )


def should_abstain(question: str) -> bool:
    return abstain_enabled() and not _CRE_STYLE.search(question or "")


_PLAN: dict = {}
_ANSWERS: dict = {}


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

    if flags.on("QUERY"):
        from application.utils.comprehension.retrieve import prefetch_embedding

        prefetch_embedding(question)  # overlaps with the query-understanding call
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
        gap = float(os.environ.get("OWASP_CX_RERANK_GAP", "0.04"))
        close = len(comp) > 4 and (
            float(comp[0].score or 0.0) - float(comp[4].score or 0.0) < gap
        )
        if llm and close:
            pool = comp[:30]
            try:
                order = rerank_order(
                    clean, [_split_citations(h.content)[0] for h in pool], llm
                )
            except Exception:
                order = []
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
    body = body.partition("\n\nRelated questions:")[0]  # index-only text, not evidence
    return body.strip(), [
        c.strip() for c in tail.split(",") if c.strip().startswith("http")
    ]


def answer_from_candidates(
    question: str, cands: Sequence[Any], complete: Optional[CompletionFn]
) -> Optional[Tuple[str, List[str]]]:
    """Return (answer, citations) or None when no comprehension doc answers it."""
    if not enabled() or complete is None:
        return None
    from application.utils.comprehension import flags

    ckey = (question, tuple(flags.active()))
    if flags.on("CACHE"):
        got = _ANSWERS.get(ckey)
        if got and time.time() - got[0] < 3600:
            return got[1]
    out = _answer_decomposed(question, complete) if flags.on("DECOMPOSE") else None
    if out is None:
        out = _answer(question, cands, complete)
    if flags.on("CACHE") and out is not None:
        _ANSWERS[ckey] = (time.time(), out)
        if len(_ANSWERS) > 512:
            _ANSWERS.pop(next(iter(_ANSWERS)))
    return out


_MULTIPART_RE = re.compile(
    r"\?.+\?|;|\b(and also|as well as|and then|after that)\b|"
    r",?\s+and\s+(what|how|who|when|which|where|why|is|are|does|do)\b",
    re.I,
)


def looks_multipart(question: str) -> bool:
    """Cheap check so the splitting call only runs for questions that may have several parts."""
    return bool(_MULTIPART_RE.search(question or ""))


def _answer_decomposed(
    question: str, complete: CompletionFn
) -> Optional[Tuple[str, List[str]]]:
    """Answer each part of a multi-part question on its own, then combine (None = not multi-part)."""
    if not looks_multipart(question):
        return None
    from application.utils.comprehension import flags
    from application.utils.comprehension.extras import understand_query

    helper = flags.helper_llm()
    if helper is None:
        return None
    try:
        parts = understand_query(question, helper).get("parts") or []
    except Exception:
        return None
    if len(parts) < 2:
        return None
    lines: List[str] = []
    cites: List[str] = []
    found = 0
    for i, part in enumerate(parts[:4], 1):
        res = _answer(part, merge_with_dedicated(part, []), complete)
        if res:
            found += 1
            lines.append(f"{i}. {res[0]}")
            cites += [c for c in res[1] if c not in cites]
        else:
            lines.append(f"{i}. {part} - not found in the indexed sources.")
    return ("\n".join(lines), cites) if found else None


def _answer_from_whole_project(
    question: str, complete: CompletionFn
) -> Optional[Tuple[str, List[str]]]:
    """One-project questions: let the model read the project's whole text (None -> normal path)."""
    from application.utils.comprehension.retrieve import project_sources

    sources = project_sources(question)
    if not sources:
        return None

    def llm(system: str, user: str) -> str:
        return complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )

    answer, cites = synthesize(question, sources, llm)
    return (answer, cites) if answer else None


def think_effort() -> str:
    """OWASP_CX_THINK_EFFORT: '' (model default), low, medium or high thinking budget."""
    v = (os.environ.get("OWASP_CX_THINK_EFFORT") or "").strip().lower()
    return v if v in ("low", "medium", "high") else ""


def synthesis_model() -> str:
    """Model used for the final answer ('' = the default chat model)."""
    return (os.environ.get("OWASP_COMPREHENSION_MODEL") or "").strip()


def _answer(
    question: str, cands: Sequence[Any], complete: CompletionFn
) -> Optional[Tuple[str, List[str]]]:
    from application.utils.comprehension import flags

    model = synthesis_model()
    effort = "disable" if flags.on("FAST") else think_effort()
    if model or effort:
        from application.prompt_client import litellm_router

        call = litellm_router.system_user_fn(
            model or os.environ.get("CRE_LLM_CHAT_MODEL", "gemini/gemini-2.5-flash"),
            temperature=0.0,
            # Thinking tokens bill as output and add seconds: off, or a small budget.
            extra_try_kwargs={"reasoning_effort": effort} if effort else None,
        )
        complete = lambda msgs: call(
            msgs[0]["content"], msgs[1]["content"]
        )  # noqa: E731
    from application.utils.comprehension import flags

    if flags.on("LONGCTX"):
        whole = _answer_from_whole_project(question, complete)
        if whole is not None:
            return whole
    hits = [c for c in cands if is_comprehension_hit(c)]
    # Overviews first: they state structure; claims/summaries add detail.
    from application.utils.comprehension import flags

    if not flags.on("RERANK"):
        hits.sort(
            key=lambda h: (
                0 if (getattr(h, "url", "") or "").endswith("-overview") else 1
            )
        )
    hits = hits[: 16 if flags.on("MERGED") else max_sources()]
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

    if flags.on("MERGED"):
        numbered = "\n\n".join(f"[{i + 1}] {t}" for i, (t, _) in enumerate(sources))
        data = extras.parse_json(
            llm(extras.MERGED_SYSTEM, f"Message: {question}\n\nSources:\n{numbered}")
        )
        ans = str(data.get("answer") or "").strip()
        if not ans or ans.upper().startswith("UNKNOWN"):
            clar = str(data.get("clarify") or "").strip()
            return (clar, []) if clar else None
        used = sorted(
            {
                int(n)
                for n in re.findall(r"\[(\d+)\]", ans)
                if 0 < int(n) <= len(sources)
            }
        )
        merged_cites: List[str] = []
        for i in used:
            for c in sources[i - 1][1]:
                if c not in merged_cites:
                    merged_cites.append(c)
        return ans, merged_cites

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
        if hl and not extras.cheap_verify(answer, [t for t, _ in sources]):
            numbered = "\n\n".join(f"[{i + 1}] {t}" for i, (t, _) in enumerate(sources))
            try:
                _, answer = extras.verify_answer(ask, answer, numbered, hl)
            except Exception:
                pass
    return (answer, cites) if answer else None
