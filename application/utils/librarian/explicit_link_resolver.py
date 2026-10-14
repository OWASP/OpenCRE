"""Module C.0.5 — deterministic explicit-CRE fast path (Week 2). No ML.

If a section's text already cites a CRE id (``ddd-ddd``, plain or inside an
``opencre.org/cre/<id>`` link), resolve it directly against the set of known
CRE ids and bypass retrieval entirely.

Rules:
- **Authoritative URLs** — one or more known ``opencre.org/cre/<id>`` citations
  auto-link *all* of those ids (human-written, skip ML).
- **Bare ids** — only a single known ``ddd-ddd`` auto-links; unknown or
  mutually conflicting bare references never auto-link (review).

Gate (PR 2): 100% correctness on the explicit golden-dataset slice. Any
regression here is a merge blocker.

The known-id set is injected (``Container[str]``) so this module stays
dependency-free: production wires ``cre.external_id`` values from the hub.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import re
from dataclasses import dataclass
from enum import Enum
from typing import Container, List, Tuple

# Word boundaries keep e.g. "1234-567" and "027-5555" from partially matching.
CRE_ID_RE = re.compile(r"\b\d{3}-\d{3}\b")

# Human-authored OpenCRE links in markdown (authoritative when present).
OPENCRE_CRE_URL_RE = re.compile(
    r"https?://(?:www\.)?opencre\.org/cre/(\d{3}-\d{3})\b",
    re.IGNORECASE,
)


class ResolutionOutcome(str, Enum):
    # No CRE reference in the text — continue to the semantic path (C.1+).
    no_reference = "no_reference"
    # Exactly one known CRE id — deterministic auto-link, skip retrieval.
    resolved = "resolved"
    # One or more known OpenCRE URL citations — auto-link all (authoritative).
    authoritative = "authoritative"
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


def extract_opencre_url_cre_ids(text: str) -> List[str]:
    """CRE ids cited via ``opencre.org/cre/<id>`` URLs only, deduped, in order."""
    seen = set()
    refs: List[str] = []
    for match in OPENCRE_CRE_URL_RE.findall(text or ""):
        if match not in seen:
            seen.add(match)
            refs.append(match)
    return refs


def resolve(text: str, known_cre_ids: Container[str]) -> Resolution:
    """Deterministically resolve explicit CRE references in one section.

    OpenCRE URL citations are treated as human-authoritative: every *known*
    URL id is auto-linked (outcome ``authoritative``) and retrieval is skipped.
    Bare ``ddd-ddd`` mentions keep the original single-id / conflict rules.
    """
    url_refs = extract_opencre_url_cre_ids(text)
    if url_refs:
        known = tuple(ref for ref in url_refs if ref in known_cre_ids)
        unknown = tuple(ref for ref in url_refs if ref not in known_cre_ids)
        if known and not unknown:
            return Resolution(ResolutionOutcome.authoritative, known, ())
        if known and unknown:
            # Partial: still surface known ids for review, do not auto-link.
            return Resolution(ResolutionOutcome.unknown_reference, known, unknown)
        return Resolution(ResolutionOutcome.unknown_reference, (), unknown)

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
