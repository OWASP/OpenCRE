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

from dataclasses import dataclass
from datetime import datetime
from typing import List, Union

from application.utils.librarian.decision_engine import decide
from application.utils.librarian.emitter import emit
from application.utils.librarian.schemas import LinkProposal, ReviewItem
from application.utils.librarian.section_validator import (
    SectionValidationError,
    section_from_queue_row,
)

Envelope = Union[LinkProposal, ReviewItem]


@dataclass(frozen=True)
class RunStats:
    """Counts for one pipeline run. ``skipped`` are rows rejected at the C.0 boundary."""

    total: int
    linked: int
    review: int
    skipped: int


@dataclass(frozen=True)
class RunResult:
    envelopes: List[Envelope]
    stats: RunStats


class LibrarianPipeline:
    """Runs C.0 -> C.4 over a knowledge source, emitting one envelope per valid row.

    ``scaler`` is a fitted C.3 ``TemperatureScaler`` (the persisted ``T``);
    ``threshold`` is the C.4 auto-link bar. Components are duck-typed to their one
    method each (``source.items`` / ``retriever.retrieve`` / ``reranker.rerank`` /
    ``scaler.confidence``) so tests inject trivial stubs.
    """

    def __init__(
        self,
        source,
        retriever,
        reranker,
        scaler,
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
        linked = review = skipped = total = 0
        for item in self._source.items():
            total += 1
            try:
                section = section_from_queue_row(item)
            except SectionValidationError:
                skipped += 1  # rejected at the boundary; not a decision
                continue

            audit = self._retriever.retrieve(section.text)
            audit = self._reranker.rerank(section.text, audit)
            reranked = [c for c in audit.reranked if c.score_rerank is not None]
            logits = [float(c.score_rerank) for c in reranked]
            cre_ids = [c.cre_id for c in reranked]
            confidence = self._scaler.confidence(logits) if logits else 0.0

            result = decide(confidence, cre_ids, threshold=self._threshold)
            envelope = emit(section, audit, result, pipeline_run_id=self._run_id, at=at)
            envelopes.append(envelope)
            if isinstance(envelope, LinkProposal):
                linked += 1
            else:
                review += 1

        return RunResult(
            envelopes=envelopes,
            stats=RunStats(total=total, linked=linked, review=review, skipped=skipped),
        )
