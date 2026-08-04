"""Module C.4 — the pipeline (Week 6b). The assembly line.

Wires the librarian end to end for a stream of ``knowledge_queue`` rows:

    C.0  section_from_queue_row   row  -> validated Section (malformed rows skipped)
    C.1  retriever.retrieve       text -> RetrievalAudit.candidates (top-K)
    C.2  reranker.rerank          text -> RetrievalAudit.reranked   (top-N logits)
    C.3  scaler.confidence        logits -> one calibrated confidence
    C.4  decide + emit            confidence -> LinkProposal | ReviewItem

Every stage is an injected seam (``source``/``retriever``/``reranker``/``scaler``),
so the whole pipeline runs hermetically with stubs — no DB, embedding model, or
cross-encoder. It is inherently **dry-run**: it builds envelopes and never persists
(the queue write-back and graph writes are W8). ``pipeline_run_id`` and the ``at``
timestamp are injected, never read from the clock, so a run is reproducible.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Protocol, Sequence, Union

from application.utils.librarian.decision_engine import decide
from application.utils.librarian.emitter import emit
from application.utils.librarian.schemas import (
    KnowledgeQueueItem,
    LinkProposal,
    RetrievalAudit,
    ReviewItem,
)
from application.utils.librarian.section_validator import (
    SectionValidationError,
    section_from_queue_row,
)

logger = logging.getLogger(__name__)

Envelope = Union[LinkProposal, ReviewItem]


# The injected seams, as Protocols rather than bare duck-typing: each stage is
# structurally one method, so a stub only has to provide that method, while
# ``make mypy --strict`` can still check the call sites and every implementation
# the live wiring passes in (W8).


class KnowledgeSource(Protocol):
    """C.0 input: yields ``knowledge_queue`` rows, validated or still raw dicts."""

    def items(self) -> Iterable[Union[KnowledgeQueueItem, Dict[str, Any]]]: ...


class Retriever(Protocol):
    """C.1: text -> shortlist of candidate CREs."""

    def retrieve(self, text: str) -> RetrievalAudit: ...


class Reranker(Protocol):
    """C.2: re-sorts a shortlist, filling ``reranked`` with cross-encoder logits."""

    def rerank(self, text: str, audit: RetrievalAudit) -> RetrievalAudit: ...


class Scaler(Protocol):
    """C.3: reranked logits -> one calibrated top-1 confidence."""

    def confidence(self, logits: Sequence[float]) -> float: ...


@dataclass(frozen=True)
class RunStats:
    """Counts for one pipeline run.

    ``skipped`` are rows rejected at the C.0 boundary (a clean, typed refusal);
    ``errored`` are rows a later stage raised on, which are contained per row so
    one bad row cannot discard the whole batch. The two are separate because a
    boundary rejection is expected input hygiene while an error is a fault worth
    investigating.
    """

    total: int
    linked: int
    review: int
    skipped: int
    errored: int = 0


@dataclass(frozen=True)
class RunResult:
    envelopes: List[Envelope]
    stats: RunStats


class LibrarianPipeline:
    """Runs C.0 -> C.4 over a knowledge source, emitting one envelope per valid row.

    ``scaler`` is a fitted C.3 ``TemperatureScaler`` (the persisted ``T``);
    ``threshold`` is the C.4 auto-link bar. Each component is structurally one
    method (``KnowledgeSource`` / ``Retriever`` / ``Reranker`` / ``Scaler``), so
    tests inject trivial stubs while the call sites stay type-checked.

    Rows are independent: a row rejected at the C.0 boundary counts as ``skipped``
    and a row whose later stages raise counts as ``errored``, and neither stops the
    run.
    """

    def __init__(
        self,
        source: KnowledgeSource,
        retriever: Retriever,
        reranker: Reranker,
        scaler: Scaler,
        *,
        threshold: float,
        pipeline_run_id: str
    ) -> None:
        self._source = source
        self._retriever = retriever
        self._reranker = reranker
        self._scaler = scaler
        self._threshold = threshold
        self._run_id = pipeline_run_id

    def run(self, *, at: datetime) -> RunResult:
        envelopes: List[Envelope] = []
        linked = review = skipped = errored = total = 0
        for item in self._source.items():
            total += 1
            try:
                section = section_from_queue_row(item)
            except SectionValidationError:
                skipped += 1  # rejected at the boundary; not a decision
                continue

            # Contain failures per row. With hermetic stubs nothing here raises,
            # but these seams become live DB / embedding / cross-encoder calls in
            # W8, where one timeout or one malformed candidate must not throw away
            # every envelope the run has already built.
            try:
                audit = self._retriever.retrieve(section.text)
                audit = self._reranker.rerank(section.text, audit)
                reranked = [c for c in audit.reranked if c.score_rerank is not None]
                logits = [float(c.score_rerank) for c in reranked]
                cre_ids = [c.cre_id for c in reranked]
                confidence = self._scaler.confidence(logits) if logits else 0.0

                result = decide(confidence, cre_ids, threshold=self._threshold)
                envelope = emit(
                    section, audit, result, pipeline_run_id=self._run_id, at=at
                )
            except Exception:
                errored += 1
                logger.warning(
                    "librarian pipeline: chunk %s (artifact %s) failed after the C.0 "
                    "boundary; skipping this row",
                    section.chunk_id,
                    section.artifact_id,
                    exc_info=True,
                )
                continue

            envelopes.append(envelope)
            if isinstance(envelope, LinkProposal):
                linked += 1
            else:
                review += 1

        return RunResult(
            envelopes=envelopes,
            stats=RunStats(
                total=total,
                linked=linked,
                review=review,
                skipped=skipped,
                errored=errored,
            ),
        )
