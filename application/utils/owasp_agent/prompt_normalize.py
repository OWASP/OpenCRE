"""Lightweight NLP normalize for OWASP-agent prompts before embed/retrieve.

Strips politeness / paraphrase filler so similarity and entity answers are not
distorted by ``please``, ``(source: …)``, etc. Prefers NLTK when available;
falls back to a fixed filler set (no hard dependency for prod chat).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import FrozenSet, Optional

# Domain fillers / paraphrase noise (kept even when NLTK stopwords load).
_EXTRA_FILLERS: FrozenSet[str] = frozenset(
    {
        "please",
        "thanks",
        "thank",
        "pls",
        "plz",
        "just",
        "really",
        "simply",
        "basically",
        "quick",
        "question",
        "sentence",
        "one",
        "tell",
        "me",
        "about",
        "regarding",
        "concerning",
        "source",
        "owasp.org",
        "according",
        "org",
    }
)

# Never drop these even if they appear in stopword lists.
_KEEP: FrozenSet[str] = frozenset(
    {
        "ai",
        "owasp",
        "asvs",
        "cre",
        "zap",
        "llm",
        "top",
        "ten",
        "board",
        "chapter",
        "project",
        "projects",
        "who",
        "what",
        "where",
        "when",
        "how",
        "why",
        "which",
        "not",
        "no",
        "vs",
        "versus",
    }
)

_SOURCE_PAREN_RE = re.compile(
    r"\(\s*source\s*:[^)]*\)",
    re.IGNORECASE,
)
# Adversarial / probe wrappers that dilute embeddings (not factual content).
_WRAPPER_PAREN_RE = re.compile(
    r"\(\s*(metadata\s+only|meta\s+only|facts?\s+only)\s*\)",
    re.IGNORECASE,
)
_WRAPPER_PHRASE_RE = re.compile(
    r"\b(no preamble|be precise|answer from the owasp index|"
    r"metadata only|cite the page if you can)\b[:\s,-]*",
    re.IGNORECASE,
)
_MULTI_SPACE_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def _nltk_stopwords() -> Optional[FrozenSet[str]]:
    try:
        from nltk.corpus import stopwords  # type: ignore[import-untyped]

        return frozenset(w.lower() for w in stopwords.words("english"))
    except Exception:
        return None


def _tokenize(text: str) -> list[str]:
    try:
        from nltk.tokenize import word_tokenize  # type: ignore[import-untyped]

        return list(word_tokenize(text))
    except Exception:
        return re.findall(r"[A-Za-z0-9][A-Za-z0-9\-/+]*|'s", text)


def normalize_prompt(prompt: str) -> str:
    """Return a filler-stripped prompt suitable for embedding / retrieve.

    Casefolds content so ALL-CAPS adversarial prompts still match embeddings.
    Preserves content tokens (project names, people, topics). Empty input stays
    empty; if stripping would wipe everything, return the lightly cleaned
    original (also casefolded).
    """
    raw = (prompt or "").strip()
    if not raw:
        return ""
    cleaned = _SOURCE_PAREN_RE.sub(" ", raw)
    cleaned = _WRAPPER_PAREN_RE.sub(" ", cleaned)
    cleaned = _WRAPPER_PHRASE_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("—", " ").replace("–", " ")
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned).strip()
    light = cleaned.casefold()

    stops = _nltk_stopwords() or frozenset()
    drop = stops | _EXTRA_FILLERS
    tokens = _tokenize(cleaned)
    kept: list[str] = []
    for tok in tokens:
        low = tok.casefold()
        if low in _KEEP:
            kept.append(low)
            continue
        if low in drop:
            continue
        if tok in {".", ",", "?", "!", ";", ":", "(", ")", "'", '"', "''", "``"}:
            continue
        kept.append(low)
    out = _MULTI_SPACE_RE.sub(" ", " ".join(kept)).strip(" .?!")
    return out if out else light
