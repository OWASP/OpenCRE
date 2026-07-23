"""Module C.0.5 — deterministic explicit-CRE fast path (Week 2). No ML.

If a section's text already cites a CRE id (``ddd-ddd``, plain or inside an
``opencre.org/cre/<id>`` link), resolve it directly against the set of known
CRE ids and bypass retrieval entirely. The fail-safe rule from the proposal:
unknown or mutually conflicting references never auto-link — they fall
through to human review; only a single, known reference resolves.

Gate (PR 2): 100% correctness on the explicit golden-dataset slice. Any
regression here is a merge blocker.

The known-id set is injected (``Container[str]``) so this module stays
dependency-free: the harness seeds it from the golden dataset today; the
DB-backed registry of real ``cre.external_id`` values arrives with the
retriever (W3).
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Container, List, Tuple

# Word boundaries keep e.g. "1234-567" and "027-5555" from partially matching.
CRE_ID_RE = re.compile(r"\b\d{3}-\d{3}\b")


class ResolutionOutcome(str, Enum):
    # No CRE reference in the text — continue to the semantic path (C.1+).
    no_reference = "no_reference"
    # Exactly one known CRE id — deterministic auto-link, skip retrieval.
    resolved = "resolved"
    # Reference(s) found but none/some are known CRE ids — route to review.
    unknown_reference = "unknown_reference"
    # Multiple distinct known ids in one section — ambiguous, route to review.
    conflicting_references = "conflicting_references"


@dataclass(frozen=True)
class Resolution:
    outcome: ResolutionOutcome
    # Known ids, deduped, in order of first appearance. Non-empty iff some
    # reference resolved; for conflicting outcomes these become the
    # ReviewItem's suggested_links.
    cre_ids: Tuple[str, ...]
    # References that matched the CRE-id pattern but are not known ids.
    unknown_refs: Tuple[str, ...]


def extract_cre_refs(text: str) -> List[str]:
    """All CRE-id-shaped references in the text, deduped, in order."""
    seen = set()
    refs = []
    for match in CRE_ID_RE.findall(text):
        if match not in seen:
            seen.add(match)
            refs.append(match)
    return refs


def resolve(text: str, known_cre_ids: Container[str]) -> Resolution:
    """Deterministically resolve explicit CRE references in one section."""
    refs = extract_cre_refs(text)
    if not refs:
        return Resolution(ResolutionOutcome.no_reference, (), ())

    known = tuple(ref for ref in refs if ref in known_cre_ids)
    unknown = tuple(ref for ref in refs if ref not in known_cre_ids)

    if unknown:
        return Resolution(ResolutionOutcome.unknown_reference, known, unknown)
    if len(known) > 1:
        return Resolution(ResolutionOutcome.conflicting_references, known, ())
    return Resolution(ResolutionOutcome.resolved, known, ())
