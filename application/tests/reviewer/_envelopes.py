"""Shared fixtures for Module D tests.

Rows are seeded through the real ``DbEnvelopeSink`` wherever possible, so these
tests exercise the actual C -> D handoff: D reads exactly what C writes, or the
test fails. The envelope builders mirror the librarian's own test fixtures.
"""

from datetime import datetime, timezone

from application.utils.librarian.schemas import (
    SCHEMA_VERSION,
    CreCandidate,
    KnowledgeSnapshot,
    LinkProposal,
    Locator,
    ProposedLink,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
    SourceRef,
    UpdateDetection,
)

AT = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
RUN = "run-1"


def _knowledge() -> KnowledgeSnapshot:
    return KnowledgeSnapshot(
        text="Verify passwords are at least 12 characters.",
        source=SourceRef(
            type="github",
            repo="OWASP/ASVS",
            commit_sha="abc1234567890",
            committed_at=AT,
        ),
        locator=Locator(kind="repo_path", id="a.md", path="a.md"),
    )


def _audit() -> RetrievalAudit:
    return RetrievalAudit(
        retriever="stub/1.0.0",
        candidates=[CreCandidate(cre_id="616-305", score_vector=0.9)],
        reranked=[CreCandidate(cre_id="616-305", score_rerank=4.0)],
        threshold=0.8,
    )


def review(chunk_id: str = "chk:1", run: str = RUN) -> ReviewItem:
    return ReviewItem(
        schema_version=SCHEMA_VERSION,
        review_id=f"review:{chunk_id}",
        chunk_id=chunk_id,
        artifact_id="art:1",
        pipeline_run_id=run,
        created_at=AT,
        reason_code=ReasonCode.below_threshold,
        knowledge=_knowledge(),
        retrieval=_audit(),
        suggested_links=[
            ProposedLink(cre_id="616-305", link_type="Related to", confidence=0.42)
        ],
        update_detection=UpdateDetection(is_update=False),
    )


def linked(chunk_id: str = "chk:9", run: str = RUN) -> LinkProposal:
    return LinkProposal(
        schema_version=SCHEMA_VERSION,
        chunk_id=chunk_id,
        artifact_id="art:1",
        pipeline_run_id=run,
        classified_at=AT,
        knowledge=_knowledge(),
        retrieval=_audit(),
        links=[
            ProposedLink(
                cre_id="616-305",
                link_type="Automatically linked to",
                confidence=0.95,
            )
        ],
        update_detection=UpdateDetection(is_update=False),
    )
