"""MyOpenCRE automated mapping: the Librarian applied to a user's standard.

RFC user-auth-myopencre TODO 3, built on the maintainer decision in #965: there
is no second mapping stack. ``run_mapping`` takes a user standard's PENDING
sections and runs them through the same C.1 retrieve, C.2 rerank, C.3
calibrate and C.4 decide the OIE pipeline runs, then records one outcome per
section:

- ``AUTO_MAPPED``   confidence at or above the Librarian's link threshold
- ``NEEDS_REVIEW``  below it (the candidate is kept as the reviewer's hint)
- ``UNMAPPABLE``    no candidate at all

The status rule is ``decision_engine.decide`` itself, not a re-derivation of
it, so MyOpenCRE and the pipeline cannot disagree about what a confidence
means. ``USER_CONFIRMED`` and ``USER_REJECTED`` rows are never read or written
here: user decisions are ground truth, and the write path in the database
refuses to move them even if asked.

This runs in a worker (the rq entry point is ``run_mapping_job``), which is
why it may load the cross-encoder; the web process gets shortlists from
``/rest/v1/link/suggest`` instead and never pays for the model.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence

from application.database.db import SectionStatus
from application.utils.librarian.config_loader import LibrarianConfig, load_config
from application.utils.librarian.decision_engine import Decision, ReasonCode, decide
from application.utils.librarian.factory import LibrarianComponents
from application.utils.librarian.link_suggest import _resolve_cre

#: Which rows a run considers. Re-indexing the graph re-runs AUTO_MAPPED and
#: NEEDS_REVIEW too (RFC TODO 3); a normal run only drains PENDING.
PENDING_ONLY: Sequence[str] = (SectionStatus.PENDING.value,)
REMAP_AFTER_REINDEX: Sequence[str] = (
    SectionStatus.PENDING.value,
    SectionStatus.AUTO_MAPPED.value,
    SectionStatus.NEEDS_REVIEW.value,
)


@dataclass
class MappingSummary:
    """Outcome of one ``run_mapping`` call; ``to_dict`` for job results."""

    standard_id: str
    threshold: float
    considered: int = 0
    auto_mapped: int = 0
    needs_review: int = 0
    unmappable: int = 0
    #: sections whose stage raised; left as they were so the next run retries
    errored: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _store_id_for(database: Any, candidate_id: str) -> Optional[str]:
    """The CRE row id to persist for a retriever candidate, or None.

    Retrievers hand back whatever the embeddings pool was keyed by (the CRE's
    internal id today). ``cre_db_id`` is defined as the internal id and is
    validated at write time, so a candidate the graph cannot resolve is not
    stored: the section goes to review with no suggestion rather than carrying
    a dangling reference.
    """
    cre = _resolve_cre(database, candidate_id)
    if cre is None or not cre.id:
        return None
    internal_id: Optional[str] = database.get_cre_internal_id(cre.id)
    return internal_id


def run_mapping(
    standard_id: str,
    database: Any,
    *,
    components: Optional[LibrarianComponents] = None,
    config: Optional[LibrarianConfig] = None,
    statuses: Sequence[str] = PENDING_ONLY,
) -> MappingSummary:
    """Map every section of ``standard_id`` in ``statuses`` and persist outcomes.

    Idempotent: a section leaves PENDING on success, so re-running the job
    processes only what the previous run did not finish. Per-section failures
    are contained and counted, never fatal to the batch.
    """
    config = config or load_config()
    if components is None:
        from application.utils.librarian.factory import build_components

        components = build_components(database, config=config)
    summary = MappingSummary(standard_id=standard_id, threshold=config.link_threshold)

    for row in database.get_user_standard_sections_by_status(standard_id, statuses):
        summary.considered += 1
        try:
            audit = components.retriever.retrieve(row.section_text)
            audit = components.reranker.rerank(row.section_text, audit)
            reranked = [c for c in audit.reranked if c.score_rerank is not None]
            logits = [float(c.score_rerank) for c in reranked]
            cre_ids = [c.cre_id for c in reranked] or [
                c.cre_id for c in audit.candidates
            ]
            confidence = components.scaler.confidence(logits) if logits else 0.0
            result = decide(confidence, cre_ids, threshold=config.link_threshold)
        except Exception:
            summary.errored += 1
            logger.warning(
                "mapping job: section %s of standard %s failed; left for retry",
                row.section_id,
                standard_id,
                exc_info=True,
            )
            continue

        if result.reason_code is ReasonCode.no_candidates:
            database.set_section_mapping(
                row.id,
                cre_db_id=None,
                confidence=None,
                status=SectionStatus.UNMAPPABLE.value,
            )
            summary.unmappable += 1
            continue

        cre_db_id = _store_id_for(database, result.cre_ids[0])
        if result.decision is Decision.linked and cre_db_id is not None:
            status = SectionStatus.AUTO_MAPPED.value
            summary.auto_mapped += 1
        else:
            # Below threshold, or a candidate the graph could not resolve: a
            # human decides, with the Librarian's confidence beside it.
            status = SectionStatus.NEEDS_REVIEW.value
            summary.needs_review += 1
        database.set_section_mapping(
            row.id,
            cre_db_id=cre_db_id,
            confidence=round(result.confidence, 4),
            status=status,
        )

    logger.info("mapping job: %s", summary.to_dict())
    return summary


def run_mapping_job(standard_id: str, db_connection_str: str) -> Dict[str, Any]:
    """rq entry point: connect, map the PENDING sections, return the summary.

    Registered by dotted path, like ``run_gap_pair_job``, so the worker needs
    no import of the web app.
    """
    from application.cmd.cre_main import db_connect

    database = db_connect(path=db_connection_str)
    return run_mapping(standard_id, database).to_dict()


def enqueue_mapping(standard_id: str, db_connection_str: str) -> str:
    """Queue ``run_mapping_job`` on the mapping queue; returns the rq job id."""
    from rq import Queue

    from application.utils import redis

    conn = redis.connect()  # type: ignore[no-untyped-call]
    queue = Queue(
        name=os.environ.get("CRE_MAPPING_QUEUE_NAME", "mapping"), connection=conn
    )
    job = queue.enqueue_call(
        description=f"mapping:{standard_id}",
        func="application.utils.mapping_job.run_mapping_job",
        kwargs={"standard_id": standard_id, "db_connection_str": db_connection_str},
        timeout=1800,
    )
    return str(job.id)


__all__ = [
    "MappingSummary",
    "PENDING_ONLY",
    "REMAP_AFTER_REINDEX",
    "enqueue_mapping",
    "run_mapping",
    "run_mapping_job",
]
