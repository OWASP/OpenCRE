"""Module C's live entry point: knowledge_queue -> C.0..C.4 -> consumed.

The counterpart to Module B's ``run_noise_filter``, and deliberately the same
shape — ``(session, pipeline_run_id, ..., dry_run) -> RunSummary`` with a
``to_json()`` the CLI prints for the orchestrator to read. B reads
``harvest_input`` and fills ``knowledge_queue``; C drains ``knowledge_queue``
and stamps ``consumed_at``.

What this module adds over ``LibrarianPipeline`` is only the two DB-facing ends.
The pipeline stays persistence-free and hermetic; this wraps it with a live
source on one side and the write-back on the other.

**Consumption is gated on persistence.** Marking a row consumed tells Module B
never to offer that chunk again, so doing it while the envelope goes nowhere
destroys the chunk outright. The runner therefore refuses to stamp anything
unless it was given a sink that reports ``persists=True`` and that sink accepted
the batch. Graph writes are still W8b; ``JsonlEnvelopeSink`` is what makes a live
drain lossless in the meantime.

**Which rows get retired.** Everything the pipeline finished with: rows that
linked, rows that routed to review, and rows refused at the C.0 boundary (a
definitive refusal — re-reading a malformed row forever helps nobody). Rows that
*errored* mid-pipeline are left unconsumed, because those are the transient
failures — an embedding timeout, a cross-encoder hiccup — that the next run
should retry. ``RowOutcome`` is what carries that distinction out of the pipeline.

**The safety path is declared, not assumed.** No detector exists yet, so the
pipeline runs behind ``NullSafetyGuard`` and every row comes back unevaluated.
That count is carried into the summary rather than left to look like a clean
result, and W8b's graph writer must refuse to run while it is non-zero.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

from application.utils.librarian.config_loader import LibrarianConfig, load_config
from application.utils.librarian.envelope_sink import EnvelopeSink
from application.utils.librarian.factory import LibrarianComponents
from application.utils.librarian.knowledge_source import DbKnowledgeSource
from application.utils.librarian.pipeline import LibrarianPipeline, RunResult
from application.utils.librarian.queue_consumer import mark_consumed

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """Outcome of one Module C run; the CLI emits this as JSON.

    ``read`` counts rows drawn from the queue, ``consumed`` counts rows actually
    stamped. They differ when rows errored (left for retry) or when the run was
    a dry run.
    """

    run_id: str
    read: int = 0
    linked: int = 0
    review: int = 0
    skipped: int = 0
    errored: int = 0
    persisted: int = 0
    consumed: int = 0
    #: Rows decided without the safety path having run. Reported rather than
    #: hidden: an unevaluated guard must not look like a clean one.
    safety_unevaluated: int = 0
    dry_run: bool = False
    #: ``ok`` only when the run has nothing to declare. A constant ``"ok"`` would
    #: be the same failure this module keeps fixing elsewhere: a field that looks
    #: like a verdict while measuring nothing. The orchestrator reads this JSON,
    #: so a run that dropped rows to errors, or decided them without the safety
    #: path, has to say so in the field a consumer actually branches on — the
    #: counts alone require the reader to know which ones are bad news.
    status: str = "ok"

    def finalize_status(self) -> None:
        """Derive ``status`` from the counts. Called once, after the run."""
        reasons = []
        if self.errored:
            reasons.append(f"{self.errored} errored")
        if self.safety_unevaluated:
            reasons.append(f"{self.safety_unevaluated} decided without the safety path")
        self.status = "degraded: " + "; ".join(reasons) if reasons else "ok"

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def run_librarian_queue(
    session: Any,
    pipeline_run_id: str,
    components: LibrarianComponents,
    config: Optional[LibrarianConfig] = None,
    *,
    at: datetime,
    sink: Optional[EnvelopeSink] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> RunSummary:
    """Drain one pipeline run's unconsumed queue rows through C.0 -> C.4.

    Args:
        session: SQLAlchemy session (caller owns connect/commit/teardown, as on
            Module B's side).
        pipeline_run_id: the run to process. Required, and it scopes both ends:
            only that run's rows are read, and it is the id stamped on every
            envelope. Draining several B runs under one id would misattribute
            provenance, so the API does not allow it.
        components: live C.1/C.2/C.3, from ``factory.build_components``.
        config: Module C settings; defaults to ``load_config()``.
        at: the run timestamp, injected rather than read from the clock so a run
            is reproducible and every envelope and every ``consumed_at`` in the
            batch share one value.
        sink: where the envelopes are persisted. Required for a real run —
            consuming a row whose envelope was discarded loses the chunk — and
            it must report ``persists=True``. A dry run may omit it.
        limit: cap on rows read in this batch; None drains the run.
        dry_run: build envelopes, persist nothing, leave ``consumed_at`` alone.

    Returns a ``RunSummary``; it does not raise on individual bad rows, which
    are counted as ``skipped`` or ``errored``. It *does* raise on a caller that
    asks for a real run with nowhere to put the results.
    """
    config = config or load_config()
    summary = RunSummary(run_id=pipeline_run_id, dry_run=dry_run)

    if not dry_run:
        if sink is None:
            raise ValueError(
                "a real run needs an EnvelopeSink: marking rows consumed while "
                "discarding their envelopes would lose those chunks. Pass a "
                "sink, or set dry_run=True."
            )
        if not sink.persists:
            raise ValueError(
                f"{type(sink).__name__} does not persist envelopes, so this run "
                "must not mark rows consumed. Use dry_run=True with it."
            )

    source = DbKnowledgeSource(session, pipeline_run_id=pipeline_run_id, limit=limit)
    pipeline = LibrarianPipeline(
        source,
        components.retriever,
        components.reranker,
        components.scaler,
        threshold=config.link_threshold,
        pipeline_run_id=pipeline_run_id,
    )

    result: RunResult = pipeline.run(at=at)
    summary.read = result.stats.total
    summary.linked = result.stats.linked
    summary.review = result.stats.review
    summary.skipped = result.stats.skipped
    summary.errored = result.stats.errored
    summary.safety_unevaluated = result.stats.safety_unevaluated

    if summary.safety_unevaluated:
        logger.warning(
            "librarian run %s: %d of %d rows were decided without the safety "
            "path (no SafetyGuard implementation yet), so ADVERSARIAL_FLAG and "
            "UPDATE_AMBIGUOUS could not fire. Their clean verdicts are defaults, "
            "not findings.",
            pipeline_run_id,
            summary.safety_unevaluated,
            summary.read,
        )

    if dry_run:
        summary.finalize_status()
        return summary

    # Persist first, retire second. If the sink raises, nothing is consumed and
    # the whole run is retried — the rows are still B's to hand back.
    assert sink is not None  # guarded above; narrows the Optional for mypy
    summary.persisted = sink.write(result.envelopes)

    finished = result.finished_row_ids()
    summary.consumed = mark_consumed(session, finished, at=at)
    session.commit()

    logger.info(
        "librarian run %s: read %d, linked %d, review %d, skipped %d, "
        "errored %d, persisted %d, consumed %d",
        pipeline_run_id,
        summary.read,
        summary.linked,
        summary.review,
        summary.skipped,
        summary.errored,
        summary.persisted,
        summary.consumed,
    )
    summary.finalize_status()
    return summary


__all__ = ["RunSummary", "run_librarian_queue"]
