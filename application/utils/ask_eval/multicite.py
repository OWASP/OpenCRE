"""Helpers for ask-eval regressions that require multi-project citations.

Used when a good answer should ground in more than one OWASP surface
(e.g. AI Exchange *and* www-board), not treat the second as contamination.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence, Union

Cite = Union[str, Mapping[str, object]]


def _cite_text(cite: Cite) -> str:
    if isinstance(cite, str):
        return cite
    for key in ("url", "path", "href", "link", "source", "id"):
        val = cite.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return str(cite)


def flatten_cites(cites: Iterable[Cite] | None) -> str:
    """Lowercased blob of all cite strings (URLs/paths)."""
    if not cites:
        return ""
    return " ".join(_cite_text(c).lower() for c in cites)


def group_covered(cites: Iterable[Cite] | None, needles: Sequence[str]) -> bool:
    """True if any needle appears in any cite (case-insensitive)."""
    blob = flatten_cites(cites)
    if not blob:
        return False
    return any(n.lower() in blob for n in needles if n)


def missing_cite_groups(
    cites: Iterable[Cite] | None,
    required_groups: Mapping[str, Sequence[str]],
) -> List[str]:
    """Return names of required groups that have no matching cite."""
    missing: List[str] = []
    for name, needles in required_groups.items():
        if not group_covered(cites, list(needles)):
            missing.append(name)
    return missing


def assert_required_cite_groups(
    cites: Iterable[Cite] | None,
    required_groups: Mapping[str, Sequence[str]],
) -> None:
    missing = missing_cite_groups(cites, required_groups)
    if missing:
        raise AssertionError(
            "answer cites missing required groups "
            f"{missing}; cites={list(cites or [])!r}"
        )
