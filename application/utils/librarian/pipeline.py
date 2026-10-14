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

from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Union,
)

from application.utils.librarian.cre_registry import CreRegistry, ground_decision
from application.utils.librarian.decision_engine import DecisionResult, decide
from application.utils.librarian.emitter import emit
from application.utils.librarian.explicit_link_resolver import (
    ResolutionOutcome,
    resolve,
)
from application.utils.librarian.safety_guard import NullSafetyGuard, SafetyGuard
from application.utils.librarian.schemas import (
    Decision,
    KnowledgeQueueItem,
    LinkProposal,
    ReasonCode,
    RetrievalAudit,
    ReviewItem,
)
from application.utils.librarian.section_validator import (
    SectionValidationError,
    section_from_queue_row,
)


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
        safety_guard: Optional[SafetyGuard] = None,
        known_cre_ids: Optional[FrozenSet[str]] = None,
        cre_id_map: Optional[Mapping[str, str]] = None,
        cre_membership: Optional[FrozenSet[str]] = None,
        cre_registry: Optional[CreRegistry] = None,
        shortlist_llm_fn: Optional[Any] = None,
        use_focus_query: bool = False,
        pref_inject: bool = True,
        prefer_audit: bool = True,
        parent_index: Optional[Any] = None,
        leaf_drilldown: bool = False,
        leaf_drilldown_resources: Sequence[str] = (),
        leaf_drilldown_force_resources: Sequence[str] = (),
        leaf_drilldown_min_children: int = 3,
        leaf_drilldown_min_sections: int = 20,
        leaf_drilldown_keep_hub: bool = False,
        leaf_drilldown_hub_first: bool = False,
        shortlist_judge_max_picks: int = 3,
        margin_gamma: Optional[float] = None,
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
        self._known_cre_ids: FrozenSet[str] = known_cre_ids or frozenset()
        self._cre_id_map: Mapping[str, str] = cre_id_map or {}
        # Optional grounded Gemini shortlist judge (lever C). None = skip;
        # hermetic tests omit it. Live factory injects default_litellm_fn.
        self._shortlist_llm_fn = shortlist_llm_fn
        self._use_focus_query = use_focus_query
        self._pref_inject = pref_inject
        self._prefer_audit = prefer_audit
        self._parent_index = parent_index
        self._leaf_drilldown = leaf_drilldown
        self._leaf_drilldown_resources = tuple(leaf_drilldown_resources or ())
        self._leaf_drilldown_force_resources = tuple(
            leaf_drilldown_force_resources or ()
        )
        self._leaf_drilldown_min_children = max(1, int(leaf_drilldown_min_children))
        self._leaf_drilldown_min_sections = max(0, int(leaf_drilldown_min_sections))
        self._leaf_drilldown_keep_hub = bool(leaf_drilldown_keep_hub)
        self._leaf_drilldown_hub_first = bool(leaf_drilldown_hub_first)
        self._shortlist_judge_max_picks = max(1, min(5, int(shortlist_judge_max_picks)))
        self._margin_gamma: Optional[float] = (
            float(margin_gamma) if margin_gamma is not None else None
        )
        self._resource_family_counts: Mapping[str, int] = {}
        # Emit-time grounding: prefer an injected registry; otherwise build from
        # membership (+ cre_id_map for canonicalisation). None membership keeps
        # hermetic stubs passthrough until they opt in.
        if cre_registry is not None:
            self._cre_registry = cre_registry
        elif cre_membership is not None:
            self._cre_registry = CreRegistry.from_membership(
                cre_membership, self._cre_id_map
            )
        else:
            self._cre_registry = CreRegistry.disabled()

    def _apply_leaf_drilldown(
        self,
        cre_ids: Sequence[str],
        query: str,
        *,
        artifact_id: str = "",
        section_text: str = "",
    ) -> list:
        """Promote Contains children over hubs when the child scores higher."""
        if not self._leaf_drilldown or not self._parent_index or not cre_ids:
            return list(cre_ids)
        from application.utils.librarian.leaf_drilldown import (
            apply_leaf_drilldown,
            resource_allows_leaf_drilldown,
            resource_family_key,
            resource_is_fine_grained,
        )

        family = resource_family_key(artifact_id)
        family_count = int(self._resource_family_counts.get(family, 0))
        force_length = bool(self._leaf_drilldown_force_resources) and (
            resource_allows_leaf_drilldown(
                artifact_id=artifact_id,
                text=section_text,
                allowed=self._leaf_drilldown_force_resources,
            )
        )
        if not force_length and not resource_is_fine_grained(
            family_count, self._leaf_drilldown_min_sections
        ):
            return list(cre_ids)

        if not resource_allows_leaf_drilldown(
            artifact_id=artifact_id,
            text=section_text,
            allowed=self._leaf_drilldown_resources,
        ):
            return list(cre_ids)

        reranker = self._reranker
        cre_texts = getattr(reranker, "_cre_texts", None)
        score_fn = getattr(reranker, "_score_fn", None)
        if not cre_texts or score_fn is None:
            return list(cre_ids)
        try:
            return apply_leaf_drilldown(
                cre_ids,
                query,
                parent_index=self._parent_index,
                cre_texts=cre_texts,
                score_fn=score_fn,
                min_children=self._leaf_drilldown_min_children,
                hub_first=self._leaf_drilldown_hub_first,
                keep_hub_in_top2=self._leaf_drilldown_keep_hub,
            )
        except Exception:
            logger.warning(
                "leaf drill-down failed; keeping pre-drill ranking",
                exc_info=True,
            )
            return list(cre_ids)

    def _sync_audit_after_drilldown(
        self, audit: RetrievalAudit, cre_ids: Sequence[str]
    ) -> RetrievalAudit:
        """Mirror drilled ``cre_ids`` into ``audit.reranked``.

        Eval scorers (B2 / full-pipeline) read ``retrieval.reranked``, not only
        ``suggested_links``. Without this sync, leaf drill-down changes the
        decide() shortlist but scoring still sees the pre-drill hubs.
        """
        if not cre_ids:
            return audit
        from application.utils.librarian.schemas import CreCandidate

        by_id: dict = {}
        for cand in list(audit.reranked or []) + list(audit.candidates or []):
            cid = getattr(cand, "cre_id", None)
            if cid and cid not in by_id:
                by_id[cid] = cand
        new_reranked = []
        seen = set()
        for cid in cre_ids:
            if not cid or cid in seen:
                continue
            seen.add(cid)
            existing = by_id.get(cid)
            if existing is not None:
                new_reranked.append(existing)
            else:
                # Drilled leaf may be outside the C.1 shortlist.
                new_reranked.append(CreCandidate(cre_id=cid, score_vector=0.0))
        for cand in audit.reranked or []:
            cid = getattr(cand, "cre_id", None)
            if cid and cid not in seen:
                seen.add(cid)
                new_reranked.append(cand)
        return audit.model_copy(update={"reranked": new_reranked})

    def _map_cre_ids(self, external_ids: Sequence[str]) -> tuple:
        return tuple(self._cre_id_map.get(cid, cid) for cid in external_ids)

    def _explicit_audit(self) -> RetrievalAudit:
        return RetrievalAudit(
            retriever="explicit-link/0.1.0",
            candidates=[],
            reranked=[],
            threshold=self._threshold,
        )

    def run(self, *, at: datetime) -> RunResult:
        envelopes: List[Envelope] = []
        outcomes: List[RowOutcome] = []
        source_labels: Dict[str, str] = {}
        linked = review = skipped = errored = total = 0
        safety_unevaluated = 0
        # Materialize once so we can census resource families for the grain gate
        # without consuming a one-shot DB cursor twice.
        batch_items = list(self._source.items())
        if self._leaf_drilldown:
            from application.utils.librarian.leaf_drilldown import (
                count_resource_families,
            )

            arts: List[str] = []
            for raw in batch_items:
                if isinstance(raw, dict):
                    arts.append(str(raw.get("artifact_id") or ""))
                else:
                    arts.append(str(getattr(raw, "artifact_id", "") or ""))
            self._resource_family_counts = count_resource_families(arts)
        else:
            self._resource_family_counts = {}

        for item in batch_items:
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
                resolution = resolve(section.text, self._known_cre_ids)
                if resolution.outcome in (
                    ResolutionOutcome.resolved,
                    ResolutionOutcome.authoritative,
                ):
                    audit = self._explicit_audit()
                    result = DecisionResult(
                        Decision.linked,
                        1.0,
                        self._map_cre_ids(resolution.cre_ids),
                        None,
                    )
                    verdict_evaluated = False
                elif resolution.outcome in (
                    ResolutionOutcome.unknown_reference,
                    ResolutionOutcome.conflicting_references,
                ):
                    audit = self._explicit_audit()
                    mapped = self._map_cre_ids(resolution.cre_ids)
                    reason = (
                        ReasonCode.no_candidates
                        if not mapped
                        else ReasonCode.below_threshold
                    )
                    result = DecisionResult(Decision.review, 1.0, mapped, reason)
                    verdict_evaluated = False
                else:
                    audit = self._retriever.retrieve(section.text)
                    from application.utils.librarian.control_name_seed import (
                        prefer_audit_ids,
                        prefer_ids_first,
                    )
                    from application.utils.librarian.cross_encoder import (
                        vector_rerank_union_ids,
                    )

                    if not audit.candidates:
                        # Empty shortlist after prior (+ relaxed sibling) cage:
                        # true coverage gap — propose a new CRE. Never CRE_GAP
                        # when the cage still has below-threshold hits.
                        from application.utils.librarian.cre_gap_suggester import (
                            suggest_gap_cre,
                        )

                        existing: set = set(self._known_cre_ids)
                        if self._cre_registry.membership is not None:
                            existing |= set(self._cre_registry.membership)
                        gap = suggest_gap_cre(section.text, existing)
                        result = DecisionResult(
                            Decision.review,
                            0.0,
                            (),
                            ReasonCode.cre_gap,
                            gap_proposal=gap,
                        )
                        verdict_evaluated = False
                    else:
                        from application.utils.librarian.control_name_seed import (
                            prefer_audit_ids,
                            prefer_ids_first,
                        )
                        from application.utils.librarian.cross_encoder import (
                            vector_rerank_union_ids,
                        )
                        from application.utils.librarian.focus_query import (
                            focus_query_text,
                        )

                        preferred = list(
                            getattr(self._retriever, "last_preferred_cre_ids", []) or []
                        )
                        retrieved = audit  # C.1 shortlist — CE must not mutate this
                        judged: List[str] = []

                        # Lever 4: ensure preferred CREs are on the CE shortlist
                        # (vector top-K may have dropped them) before focus/CE.
                        if self._pref_inject and preferred:
                            from application.utils.librarian.schemas import CreCandidate

                            have = {
                                c.cre_id
                                for c in (retrieved.candidates or [])
                                if getattr(c, "cre_id", None)
                            }
                            injected = [
                                CreCandidate(cre_id=cid, score_vector=0.01)
                                for cid in preferred
                                if cid not in have
                            ]
                            if injected:
                                retrieved = retrieved.model_copy(
                                    update={
                                        "candidates": list(retrieved.candidates or [])
                                        + injected,
                                        "retriever": (
                                            f"{retrieved.retriever}+pref-inject"
                                        ),
                                    }
                                )

                        # Lever C: grounded shortlist judge — pick up to max_picks
                        # from the retrieval allowlist only; fail open on errors.
                        focus = (
                            focus_query_text(section.text)
                            if self._use_focus_query
                            else ""
                        )
                        if self._shortlist_llm_fn is not None:
                            from application.utils.librarian.shortlist_judge import (
                                ShortlistJudgeCache,
                                candidates_from_audit,
                                default_cache_dir,
                                judge_enabled,
                                judge_shortlist,
                            )

                            if judge_enabled():
                                judge_query = focus or section.text
                                judge_cap = self._shortlist_judge_max_picks
                                judged = judge_shortlist(
                                    judge_query,
                                    candidates_from_audit(retrieved),
                                    llm_fn=self._shortlist_llm_fn,
                                    cache=ShortlistJudgeCache(
                                        disk_dir=default_cache_dir()
                                    ),
                                    max_picks=judge_cap,
                                )
                                if judged:
                                    preferred = prefer_ids_first(
                                        judged,
                                        preferred,
                                        limit=12,
                                        lead=judge_cap,
                                    )
                                    retrieved = retrieved.model_copy(
                                        update={
                                            "retriever": (
                                                f"{retrieved.retriever}+shortlist-judge"
                                            )
                                        }
                                    )

                        def _decide_from_audit(query_text: str):
                            ranked_audit = self._reranker.rerank(query_text, retrieved)
                            # Relative margin cutoff after C.2 (promoted γ=0.85).
                            if self._margin_gamma is not None:
                                from application.utils.librarian.margin_cutoff import (
                                    apply_margin_gamma,
                                )

                                filtered = apply_margin_gamma(
                                    ranked_audit.reranked or [],
                                    gamma=self._margin_gamma,
                                )
                                ranked_audit = ranked_audit.model_copy(
                                    update={"reranked": filtered}
                                )
                            # Confidence stays on CE logits (fitted T); prefer may
                            # inject into reranked so focus/CE lead window sees winners.
                            ce_logits = [
                                float(c.score_rerank)
                                for c in ranked_audit.reranked
                                if c.score_rerank is not None
                            ]
                            lead_n = self._shortlist_judge_max_picks
                            if self._prefer_audit:
                                ranked_audit = prefer_audit_ids(
                                    ranked_audit,
                                    preferred,
                                    lead=lead_n,
                                    inject_missing=True,
                                )
                            ranked_ids = vector_rerank_union_ids(ranked_audit)
                            cre_ids_local = (
                                prefer_ids_first(preferred, ranked_ids, limit=8)
                                if self._prefer_audit
                                else ranked_ids
                            )
                            conf = (
                                self._scaler.confidence(ce_logits) if ce_logits else 0.0
                            )
                            return ranked_audit, cre_ids_local, conf

                        # Cheap first pass: Standard/Version/Section-ID/Section only.
                        if focus:
                            audit, cre_ids, confidence = _decide_from_audit(focus)
                            # Miss → retry with full narrative chunk.
                            if confidence < self._threshold:
                                audit_full, cre_ids_full, conf_full = (
                                    _decide_from_audit(section.text)
                                )
                                if conf_full >= confidence:
                                    audit, cre_ids, confidence = (
                                        audit_full,
                                        cre_ids_full,
                                        conf_full,
                                    )
                        else:
                            audit, cre_ids, confidence = _decide_from_audit(
                                section.text
                            )

<<<<<<< HEAD
=======
                        query_for_drill = focus or section.text
                        pre_drill = list(cre_ids)
                        cre_ids = self._apply_leaf_drilldown(
                            cre_ids,
                            query_for_drill,
                            artifact_id=section.artifact_id,
                            section_text=section.text,
                        )
                        # Only rewrite audit.reranked when drill mutated the
                        # shortlist — otherwise coarse arms (deny path) keep
                        # pre-drill scored preds bit-identical.
                        if list(cre_ids) != pre_drill:
                            audit = self._sync_audit_after_drilldown(audit, cre_ids)

                        verdict = self._safety_guard.evaluate(section)
>>>>>>> 7208db90 (feat(librarian): promote d1-winner combo defaults (judge+cap8+top_k=3))
                        result = decide(
                            confidence,
                            cre_ids,
                            threshold=self._threshold,
                        )
                        verdict_evaluated = False

                # C.4 safety on every path (including explicit-id / CRE_GAP exits).
                verdict = self._safety_guard.evaluate(section)
                if verdict.evaluated:
                    verdict_evaluated = True
                    if verdict.adversarial or verdict.update_ambiguous:
                        result = decide(
                            result.confidence,
                            result.cre_ids,
                            threshold=self._threshold,
                            adversarial=verdict.adversarial,
                            update_ambiguous=verdict.update_ambiguous,
                        )
                if not verdict_evaluated:
                    safety_unevaluated += 1
                result = ground_decision(result, self._cre_registry)
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
