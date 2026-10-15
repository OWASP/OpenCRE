"""Derive searchable project aliases from ingested metadata (not brand hardcodes)."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

_STOP = frozenset(
    {
        "owasp",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "to",
        "on",
        "in",
        "project",
        "projects",
        "guide",
        "documentation",
        "applications",
        "application",
        "top",
        "10",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def derive_project_aliases(
    name: str,
    key: str = "",
    tags: Optional[Sequence[str]] = None,
    *,
    extra: Optional[Sequence[str]] = None,
    url: str = "",
    description: str = "",
) -> List[str]:
    """Build alias strings from name/key/tags/url tokens already in the record."""
    out: List[str] = []

    def _add(raw: str) -> None:
        t = " ".join((raw or "").strip().lower().split())
        if not t or t in _STOP:
            return
        if t not in out:
            out.append(t)
        compact = t.replace(" ", "")
        if compact and compact not in out and len(compact) >= 2:
            out.append(compact)

    key_s = (key or "").replace("-", " ").replace("_", " ").strip()
    if key_s:
        _add(key_s)

    name_s = re.sub(r"^owasp\s+", "", (name or "").strip(), flags=re.IGNORECASE)
    name_s = re.sub(r"\s+project$", "", name_s, flags=re.IGNORECASE).strip()
    if name_s:
        _add(name_s)

    words = [
        w.lower()
        for w in _TOKEN_RE.findall(name_s)
        if w.lower() not in _STOP and len(w) > 1
    ]
    if len(words) >= 2:
        # Short tokens kept whole (ai, ml, llm, genai); else first letter.
        parts: List[str] = []
        for w in words:
            if len(w) <= 4:
                parts.append(w)
            else:
                parts.append(w[0])
        initials = "".join(parts)
        if 2 <= len(initials) <= 12:
            _add(initials)
        # Also classic first-letter acronym (AI Exchange → ae).
        letters = "".join(w[0] for w in words)
        if 2 <= len(letters) <= 6:
            _add(letters)

    for tag in tags or []:
        for piece in re.split(r"[\s,/|;]+", str(tag or "")):
            piece = piece.strip()
            # Skip ultra-short tags as aliases (ai, ml) — too many false positives.
            if len(piece) >= 3:
                _add(piece)
    # Phrase aliases from description when they name a project family.
    for m in re.finditer(
        r"\b((?:genai|llm|ai)\s+security(?:\s+project)?)\b",
        (description or "").lower(),
    ):
        _add(m.group(1))

    for ex in extra or []:
        _add(str(ex))

    # Host tokens from project sites (e.g. owaspai.org, genai.owasp.org).
    for m in re.finditer(
        r"https?://(?:www\.)?([a-z0-9-]+)(?:\.[a-z0-9.-]+)+",
        f"{url or ''} {description or ''}",
        re.IGNORECASE,
    ):
        host = m.group(1).lower()
        if host not in ("owasp", "github", "www") and len(host) >= 3:
            _add(host)

    return out


def ensure_project_aliases(payload: dict) -> dict:
    """Return a copy of project payload with aliases filled from metadata."""
    data = dict(payload or {})
    existing = [
        str(a).strip().lower() for a in (data.get("aliases") or []) if str(a).strip()
    ]
    derived = derive_project_aliases(
        str(data.get("name") or ""),
        str(data.get("key") or ""),
        list(data.get("tags") or []),
        extra=existing,
        url=str(data.get("url") or ""),
        description=str(data.get("description") or ""),
    )
    data["aliases"] = list(dict.fromkeys(existing + derived))
    return data
