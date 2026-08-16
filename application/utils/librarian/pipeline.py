"""Module C.4 — the pipeline (Week 6b). The assembly line.

Wires the librarian end to end for a stream of ``knowledge_queue`` rows:

    C.0  section_from_queue_row   row  -> validated Section (malformed rows skipped)
    C.1  retriever.retrieve       text -> RetrievalAudit.candidates (top-K)
    C.2  reranker.rerank          text -> RetrievalAudit.reranked   (top-N logits)
    C.3  scaler.confidence        logits -> one calibrated confidence
    C.4  safety_guard.evaluate    section -> blocking flags
    C.4  decide + emit            confidence + flags -> LinkProposal | ReviewItem

Every stage is an injected seam (``source``/``retriever``/``reranker``/``scaler``),
so the whole pipeline runs hermetically with stubs — no DB, embedding model, or
cross-encoder. ``pipeline_run_id`` and the ``at`` timestamp are injected, never
read from the clock, so a run is reproducible.

This module stays **persistence-free**: it builds envelopes and writes nothing.
What it does report, as of W8, is a ``RowOutcome`` per row, which is what lets
``queue_runner`` mark the finished rows consumed without this layer ever holding
a session. Graph writes remain out (W8b).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Union

from application.utils.librarian.decision_engine import decide
from application.utils.librarian.emitter import emit
from application.utils.librarian.safety_guard import NullSafetyGuard, SafetyGuard
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


def _source_label(item: Union[KnowledgeQueueItem, Dict[str, Any]]) -> Optional[str]:
    """B's ``llm_label`` for this row, when the source carries one.

    Fixture rows and hand-built dicts may not, so this is best-effort: a missing
    label records nothing rather than guessing ``KNOWLEDGE``, which would claim a
    confidence B never expressed.
    """
    if isinstance(item, dict):
        value = item.get("llm_label")
    else:
        value = getattr(item, "llm_label", None)
    return str(value) if value else None


def _row_id(item: Union[KnowledgeQueueItem, Dict[str, Any]]) -> Optional[str]:
    """The queue row's primary key, read before C.0 may reject the row.

    Taken off the raw item because a row that fails validation still has to be
    marked consumed — otherwise every malformed row is re-read forever.
    """
    if isinstance(item, KnowledgeQueueItem):
        return item.id
    if isinstance(item, dict):
        value = item.get("id")
        return value if isinstance(value, str) else None
    return None


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
    #: Rows whose safety verdict came back unevaluated. Non-zero means the
    #: ADVERSARIAL_FLAG / UPDATE_AMBIGUOUS path did not run for them, so their
    #: clean verdicts are defaults, not findings.
    safety_unevaluated: int = 0


class RowStatus(str, Enum):
    """What the pipeline did with one queue row."""

    linked = "linked"
    review = "review"
    skipped = "skipped"  # refused at the C.0 boundary
    errored = "errored"  # a later stage raised


@dataclass(frozen=True)
class RowOutcome:
    """Per-row result, so a caller can act on individual rows after the run.

    The queue write-back needs this: a row that reached a decision (or was
    definitively refused at the boundary) is finished and may be marked
    consumed, while an ``errored`` row must stay unconsumed so the next run
    retries it. ``RunStats`` counts alone cannot express that distinction.

    ``row_id`` is the ``knowledge_queue`` primary key and is None when the
    source yielded something without one (a hand-built fixture dict).
    """

    row_id: Optional[str]
    chunk_id: Optional[str]
    status: RowStatus


@dataclass(frozen=True)
class RunResult:
    envelopes: List[Envelope]
    stats: RunStats
    outcomes: List[RowOutcome] = field(default_factory=list)
    #: chunk_id -> the ``llm_label`` B wrote on the row it came from. Carried out
    #: of the run so the decision row can record which of B's labels it was made
    #: from; the RFC envelope has no field for it and is pinned, so it travels
    #: beside the envelopes rather than inside them.
    source_labels: Dict[str, str] = field(default_factory=dict)

    def finished_row_ids(self) -> List[str]:
        """Ids of rows that are done with — everything except ``errored``."""
        return [
            o.row_id
            for o in self.outcomes
            if o.row_id is not None and o.status != RowStatus.errored
        ]


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
        pipeline_run_id: str,
        safety_guard: Optional[SafetyGuard] = None
    ) -> None:
        self._source = source
        self._retriever = retriever
        self._reranker = reranker
        self._scaler = scaler
        self._threshold = threshold
        self._run_id = pipeline_run_id
        # Defaults to the declared-degraded guard rather than to nothing, so
        # `decide()` is always called with the safety arguments and the run can
        # report how many rows went unevaluated.
        self._safety_guard: SafetyGuard = safety_guard or NullSafetyGuard()

    def run(self, *, at: datetime) -> RunResult:
        envelopes: List[Envelope] = []
        outcomes: List[RowOutcome] = []
        source_labels: Dict[str, str] = {}
        linked = review = skipped = errored = total = 0
        safety_unevaluated = 0
        for item in self._source.items():
            total += 1
            row_id = _row_id(item)
            label = _source_label(item)
            try:
                section = section_from_queue_row(item)
            except SectionValidationError:
                skipped += 1  # rejected at the boundary; not a decision
                outcomes.append(RowOutcome(row_id, None, RowStatus.skipped))
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

                verdict = self._safety_guard.evaluate(section)
                result = decide(
                    confidence,
                    cre_ids,
                    threshold=self._threshold,
                    adversarial=verdict.adversarial,
                    update_ambiguous=verdict.update_ambiguous,
                )
                if not verdict.evaluated:
                    safety_unevaluated += 1
                envelope = emit(
                    section, audit, result, pipeline_run_id=self._run_id, at=at
                )
            except Exception:
                errored += 1
                outcomes.append(RowOutcome(row_id, section.chunk_id, RowStatus.errored))
                logger.warning(
                    "librarian pipeline: chunk %s (artifact %s) failed after the C.0 "
                    "boundary; skipping this row",
                    section.chunk_id,
                    section.artifact_id,
                    exc_info=True,
                )
                continue

            envelopes.append(envelope)
            if label is not None:
                source_labels[envelope.chunk_id] = label
            if isinstance(envelope, LinkProposal):
                linked += 1
                status = RowStatus.linked
            else:
                review += 1
                status = RowStatus.review
            outcomes.append(RowOutcome(row_id, section.chunk_id, status))

        return RunResult(
            envelopes=envelopes,
            stats=RunStats(
                total=total,
                linked=linked,
                review=review,
                skipped=skipped,
                errored=errored,
                safety_unevaluated=safety_unevaluated,
            ),
            outcomes=outcomes,
            source_labels=source_labels,
        )
