"""Suggest a new CRE id + name when the prior cage finds no good match (coverage gap).

Used after a strict prior cage leaves an empty shortlist: Module C emits a review
with ``ReasonCode.cre_gap`` and a ``Proposed new CRE`` suggestion whose
``cre_id`` does not exist in the hub and is not digit-close to any existing id.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from application.utils.librarian.problem_class import (
    ProblemClass,
    classify_problem,
)

_SECTION_LINE = re.compile(r"(?im)^Section:\s*(.+)$")
_STANDARD_LINE = re.compile(r"(?im)^Standard:\s*(.+)$")
_EXT_ID_RE = re.compile(r"^\d{3}-\d{3}$")


@dataclass(frozen=True)
class GapProposal:
    """A proposed new CRE for a coverage gap."""

    external_id: str
    name: str
    rationale: str


def _digits(ext_id: str) -> str:
    return ext_id.replace("-", "")


def too_close(candidate: str, existing: str, *, min_hamming: int = 2) -> bool:
    """True if digit-Hamming distance is strictly less than ``min_hamming``."""
    if not _EXT_ID_RE.match(candidate) or not _EXT_ID_RE.match(existing):
        return candidate == existing
    a, b = _digits(candidate), _digits(existing)
    if len(a) != len(b):
        return False
    dist = sum(x != y for x, y in zip(a, b))
    return dist < min_hamming


def _ext_id_set(existing_ids: Iterable[str]) -> Set[str]:
    return {i for i in existing_ids if isinstance(i, str) and _EXT_ID_RE.match(i)}


def _title_from_text(text: str) -> str:
    m = _SECTION_LINE.search(text or "")
    if m:
        return m.group(1).strip()[:120]
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("Standard:", "Source:", "Section-ID:", "Section:")):
            continue
        return s[:120]
    return "Untitled security control"


def propose_cre_name(text: str, problem: Optional[ProblemClass] = None) -> str:
    """Human-readable CRE name from section title + problem class."""
    problem = problem or classify_problem(text)
    title = _title_from_text(text)
    std_m = _STANDARD_LINE.search(text or "")
    std = std_m.group(1).strip() if std_m else ""
    class_label = problem.class_id.replace("_", " ")
    if title and title.lower() != "untitled security control":
        base = title
    else:
        base = class_label.title()
    if std and std.lower() not in base.lower():
        return f"{base} ({std})"[:160]
    return base[:160]


def propose_cre_external_id(
    text: str,
    existing_ids: Iterable[str],
    *,
    problem: Optional[ProblemClass] = None,
    max_attempts: int = 2000,
) -> str:
    """Pick ``ddd-ddd`` absent from ``existing_ids`` and not digit-close to any.

    Seeded from section text so the same gap re-proposes stably across runs.
    """
    problem = problem or classify_problem(text)
    known = _ext_id_set(existing_ids)
    seed = f"{problem.class_id}|{problem.family}|{_title_from_text(text)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()

    for attempt in range(max_attempts):
        mixed = hashlib.sha256(f"{digest}:{attempt}".encode()).hexdigest()
        n = int(mixed[:8], 16) % 1_000_000
        candidate = f"{n // 1000:03d}-{n % 1000:03d}"
        if candidate in known:
            continue
        if any(too_close(candidate, e) for e in known):
            continue
        return candidate

    start = int(digest[:6], 16) % 1_000_000
    for i in range(1_000_000):
        n = (start + i) % 1_000_000
        candidate = f"{n // 1000:03d}-{n % 1000:03d}"
        if candidate in known:
            continue
        if any(too_close(candidate, e) for e in known):
            continue
        return candidate
    raise RuntimeError("exhausted CRE id space while proposing a gap id")


def suggest_gap_cre(
    text: str,
    existing_ids: Iterable[str],
    *,
    problem: Optional[ProblemClass] = None,
) -> GapProposal:
    """Full gap proposal: unused distant id + descriptive name."""
    problem = problem or classify_problem(text)
    ext = propose_cre_external_id(text, existing_ids, problem=problem)
    name = propose_cre_name(text, problem)
    rationale = (
        f"CRE coverage gap for class={problem.class_id} family={problem.family}. "
        f"No prior-caged hub CRE matched; proposed new CRE {ext} ({name})."
    )
    return GapProposal(external_id=ext, name=name, rationale=rationale)


__all__ = [
    "GapProposal",
    "too_close",
    "propose_cre_name",
    "propose_cre_external_id",
    "suggest_gap_cre",
]
