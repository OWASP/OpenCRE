"""Module C.4 — envelope emitter (Week 6b). The scribe.

The decision engine (C.4) produces a verdict; this module turns that verdict, plus
the chunk's ``Section`` and the C.1/C.2 ``RetrievalAudit``, into the wire contract
Module D consumes: an RFC ``LinkProposal`` (auto-link) or ``ReviewItem`` (human
review). It only *builds* the envelope — persisting/queuing it is W8's writers.

Pure and timestamp-injected (``at`` is passed, not read from the clock) so every
branch is hermetically testable. ``update_detection`` defaults to the declared
degraded value (``is_update=False``) until the SafetyGuard lands; ``review_id`` is
derived deterministically from the chunk id so the same chunk always maps to the
same review, with no nondeterministic uuid in a pure builder.
"""

from datetime import datetime
from typing import Optional, Union

from application.utils.librarian.decision_engine import DecisionResult
from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    Decision,
    KnowledgeSnapshot,
    LinkProposal,
    ProposedLink,
    RetrievalAudit,
    ReviewItem,
    UpdateDetection,
)
from application.utils.librarian.section_validator import Section

# Link types C stamps on a ProposedLink, kept as literals so the emitter stays
# import-light and hermetic (both mirror cre_defs.LinkTypes values).
#   AUTO_LINK_TYPE      -- an auto-linked chunk (LinkProposal.links): C committed to it.
#   SUGGESTED_LINK_TYPE -- a review suggestion (ReviewItem.suggested_links): only a
#                          candidate for a human to consider, NOT an auto-link, so it
#                          must not claim "Automatically linked to".
AUTO_LINK_TYPE = "Automatically linked to"
SUGGESTED_LINK_TYPE = "Related"


class EmitterError(ValueError):
    """Raised when a DecisionResult cannot be turned into an envelope."""


def _degraded_update_detection() -> UpdateDetection:
    """The declared-degraded default until the SafetyGuard wires update detection."""
    return UpdateDetection(is_update=False)


def _snapshot(section: Section) -> KnowledgeSnapshot:
    return KnowledgeSnapshot(
        text=section.text, source=section.source, locator=section.locator
    )


def _proposed_links(result: DecisionResult, link_type: str) -> list:
    """One ProposedLink per chosen CRE (top-1), carrying the calibrated confidence.

    ``link_type`` distinguishes an auto-link (``AUTO_LINK_TYPE``) from a review
    suggestion (``SUGGESTED_LINK_TYPE``) so a not-yet-confirmed suggestion is never
    labelled as an automatic link.
    """
    return [
        ProposedLink(
            cre_id=cre_id,
            link_type=link_type,
            confidence=result.confidence,
            rationale=None,
        )
        for cre_id in result.cre_ids
    ]


def build_link_proposal(
    section: Section,
    audit: RetrievalAudit,
    result: DecisionResult,
    *,
    pipeline_run_id: str,
    at: datetime,
    update_detection: Optional[UpdateDetection] = None,
) -> LinkProposal:
    """Build the auto-link envelope. ``result.decision`` must be ``linked``."""
    if result.decision != Decision.linked:
        raise EmitterError(
            f"build_link_proposal needs a linked decision, got {result.decision}"
        )
    links = _proposed_links(result, AUTO_LINK_TYPE)
    if not links:
        raise EmitterError("a linked decision must carry at least one CRE id")
    return LinkProposal(
        schema_version=SCHEMA_VERSION,
        chunk_id=section.chunk_id,
        artifact_id=section.artifact_id,
        pipeline_run_id=pipeline_run_id,
        classified_at=at,
        knowledge=_snapshot(section),
        retrieval=audit,
        links=links,
        update_detection=update_detection or _degraded_update_detection(),
    )


def build_review_item(
    section: Section,
    audit: RetrievalAudit,
    result: DecisionResult,
    *,
    pipeline_run_id: str,
    at: datetime,
    update_detection: Optional[UpdateDetection] = None,
) -> ReviewItem:
    """Build the human-review envelope. ``result.decision`` must be ``review``."""
    if result.decision != Decision.review:
        raise EmitterError(
            f"build_review_item needs a review decision, got {result.decision}"
        )
    if result.reason_code is None:
        raise EmitterError("a review decision must carry a reason_code")
    suggested = (
        _proposed_links(result, SUGGESTED_LINK_TYPE) or None
    )  # best guess, may be empty
    return ReviewItem(
        schema_version=SCHEMA_VERSION,
        review_id=f"review:{section.chunk_id}",
        chunk_id=section.chunk_id,
        artifact_id=section.artifact_id,
        pipeline_run_id=pipeline_run_id,
        created_at=at,
        reason_code=result.reason_code,
        knowledge=_snapshot(section),
        retrieval=audit,
        suggested_links=suggested,
        update_detection=update_detection or _degraded_update_detection(),
    )


def emit(
    section: Section,
    audit: RetrievalAudit,
    result: DecisionResult,
    *,
    pipeline_run_id: str,
    at: datetime,
    update_detection: Optional[UpdateDetection] = None,
) -> Union[LinkProposal, ReviewItem]:
    """Dispatch on the verdict: ``linked`` -> LinkProposal, ``review`` -> ReviewItem."""
    builder = (
        build_link_proposal if result.decision == Decision.linked else build_review_item
    )
    return builder(
        section,
        audit,
        result,
        pipeline_run_id=pipeline_run_id,
        at=at,
        update_detection=update_detection,
    )
