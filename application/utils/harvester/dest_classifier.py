"""Decide whether a discovered GitHub repo is OpenCRE or OWASP-agent material."""

from __future__ import annotations

from typing import Iterable, Optional

OPENCRE_NAME_HINTS = (
    "asvs",
    "aisvs",
    "masvs",
    "cheatsheet",
    "cheat-sheet",
    "top-10",
    "top10",
    "top_10",
    "capec",
    "cwe",
    "pci-dss",
    "pci_dss",
    "dsomm",
    "juice-shop",
    "juiceshop",
    "secure-headers",
    "iso27001",
    "iso-27001",
    "cloud-controls",
    "api-top",
    "llm-top",
    "kubernetes-top",
    "opencre",
)
OPENCRE_TEXT_HINTS = (
    "standard",
    "cheat sheet",
    "cheatsheet",
    "guide",
    "documentation",
    "top 10",
    "top ten",
    "verification standard",
)
DOC_LANGUAGES = {None, "", "markdown", "tex", "html"}


def classify_github_repo(
    *,
    repo: str,
    description: Optional[str] = None,
    language: Optional[str] = None,
    topics: Optional[Iterable[str]] = None,
    explicit_opencre: bool = False,
) -> str:
    if explicit_opencre:
        return "opencre"
    topic_text = " ".join(topics or ())
    blob = f"{repo} {description or ''} {topic_text}".lower()
    if any(hint in blob for hint in OPENCRE_NAME_HINTS):
        return "opencre"
    lang = (language or "").strip().lower() or None
    if lang in DOC_LANGUAGES and any(hint in blob for hint in OPENCRE_TEXT_HINTS):
        return "opencre"
    return "agent"
