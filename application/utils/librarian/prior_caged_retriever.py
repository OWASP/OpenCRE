"""C.1 wrapper: classify → soft prior cage → retrieve; edition + control-name seed.

Soft cage: merge **in-prior** (allowlisted) retrieval with a **global** top-K,
then reweight so prior / preferred CREs rank above uncaged cosine hits — never
hard-wipe the shortlist. Brand-new resources still feel the prior, but a strong
global hit is not discarded.

Exposes ``last_preferred_cre_ids`` so C.4 can put edition/control seeds first.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set

from application.utils.librarian.control_name_seed import ControlNameIndex
from application.utils.librarian.cre_prior import CrePriorIndex
from application.utils.librarian.edition_remap import (
    EditionTransferService,
    parse_chunk_standard,
)
from application.utils.librarian.neighbor_transfer import NeighborTransferIndex
from application.utils.librarian.problem_class import classify_problem
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.standard_link_seed import StandardLinkIndex
from application.utils.librarian.umbrella_promote import (
    ExactNameIndex,
    ParentIndex,
    merge_preferred,
)

# Soft-cage score floors (added to score_vector before re-sort).
_PRIOR_BOOST = 0.08
_PREFERRED_BOOST = 0.18


class PriorCagedRetriever:
    """Retriever Protocol adapter that soft-cages candidates to a CRE prior."""

    def __init__(
        self,
        inner: object,
        prior: CrePriorIndex,
        *,
        enabled: bool = True,
        edition_transfer: Optional[EditionTransferService] = None,
        control_name_index: Optional[ControlNameIndex] = None,
        exact_name_index: Optional[ExactNameIndex] = None,
        parent_index: Optional[ParentIndex] = None,
        standard_links: Optional[StandardLinkIndex] = None,
        aix_llm_links: Optional[StandardLinkIndex] = None,
        neighbor_transfer: Optional[NeighborTransferIndex] = None,
    ) -> None:
        self._inner = inner
        self._prior = prior
        self._enabled = enabled
        self._edition = edition_transfer
        self._control_names = control_name_index
        self._exact_names = exact_name_index
        self._parents = parent_index
        # ``aix_llm_links`` kept as alias for older call sites / tests.
        self._standard_links = standard_links or aix_llm_links
        self._neighbors = neighbor_transfer
        #: CRE ids that should lead suggestions after the last ``retrieve``.
        self.last_preferred_cre_ids: List[str] = []

    def _relaxed_prior(self, problem) -> FrozenSet[str]:
        fam = self._prior.family_to_cres.get(problem.family, frozenset())
        key = self._prior.family_to_transfer.get(problem.family)
        transfer = (
            self._prior.transfer_to_cres.get(key, frozenset()) if key else frozenset()
        )
        return frozenset(set(fam) | set(transfer))

    def _edition_cre_ids(self, text: str) -> Set[str]:
        if self._edition is None:
            return set()
        parsed = parse_chunk_standard(text)
        if not parsed:
            return set()
        family, year, section_id = parsed
        return set(self._edition.cre_ids_for_new_section(family, year, section_id))

    def _retrieve_allowlist(
        self, text: str, allowlist: FrozenSet[str]
    ) -> RetrievalAudit:
        try:
            return self._inner.retrieve(text, allowlist=allowlist)  # type: ignore[call-arg]
        except TypeError:
            from application.utils.librarian.cre_prior import cage_candidates

            audit = self._inner.retrieve(text)  # type: ignore[attr-defined]
            return audit.model_copy(
                update={"candidates": cage_candidates(audit.candidates, allowlist)}
            )

    def _retrieve_global(self, text: str) -> RetrievalAudit:
        return self._inner.retrieve(text)  # type: ignore[attr-defined]

    def _merge_soft(
        self,
        caged: RetrievalAudit,
        global_audit: RetrievalAudit,
        *,
        prior_ids: FrozenSet[str],
        preferred: Set[str],
    ) -> List[CreCandidate]:
        """Union shortlists; preferred > prior > rest; score within each tier."""
        by_id: Dict[str, CreCandidate] = {}
        for c in list(global_audit.candidates or []) + list(caged.candidates or []):
            prev = by_id.get(c.cre_id)
            if prev is None or float(c.score_vector or 0) > float(
                prev.score_vector or 0
            ):
                by_id[c.cre_id] = c

        prior_set = set(prior_ids) | preferred

        def _tier(cid: str) -> int:
            if cid in preferred:
                return 2
            if cid in prior_set:
                return 1
            return 0

        scored = list(by_id.values())
        scored.sort(
            key=lambda c: (_tier(c.cre_id), float(c.score_vector or 0.0)),
            reverse=True,
        )
        # Light score bump so audit trail shows soft preference (optional).
        out: List[CreCandidate] = []
        for c in scored:
            base = float(c.score_vector or 0.0)
            if c.cre_id in preferred:
                base += _PREFERRED_BOOST
            elif c.cre_id in prior_set:
                base += _PRIOR_BOOST
            out.append(c.model_copy(update={"score_vector": base}))
        out.sort(
            key=lambda c: (_tier(c.cre_id), float(c.score_vector or 0.0)),
            reverse=True,
        )
        return out

    def retrieve(self, text: str) -> RetrievalAudit:
        self.last_preferred_cre_ids = []
        if not self._enabled or self._prior is None:
            return self._inner.retrieve(text)  # type: ignore[attr-defined]
        problem = classify_problem(text)
        prior_ids = self._prior.prior_for(problem)

        tags: List[str] = []
        exact_ids: List[str] = []
        edition_ids_ordered: List[str] = []
        name_ids_ordered: List[str] = []
        link_ids_ordered: List[str] = []
        neighbor_title_ids: List[str] = []
        neighbor_topic_ids: List[str] = []
        preferred: Set[str] = set()

        # Hub Links for the matched standard family (LLM, K8s, Top10, API, …).
        if self._standard_links is not None:
            link_ids_ordered = self._standard_links.preferred_for(problem, text)
            if link_ids_ordered:
                preferred |= set(link_ids_ordered)
                prior_ids = frozenset(set(prior_ids or ()) | preferred)
                tags.append("hub-links")
            bag_extra = self._standard_links.prior_extra_for(problem, text)
            if bag_extra:
                prior_ids = frozenset(set(prior_ids or ()) | set(bag_extra))
                tags.append("hub-bag")

        # Narrow neighbor winners + title/topic remap (path B). Full bag is
        # only used to boost control-name hits — never as the soft-cage itself.
        n_bag: FrozenSet[str] = frozenset()
        full_neighbor_bag: FrozenSet[str] = frozenset()
        if self._neighbors is not None:
            (
                n_bag,
                neighbor_title_ids,
                neighbor_topic_ids,
                full_neighbor_bag,
            ) = self._neighbors.apply(problem, text)
            if n_bag:
                preferred |= set(n_bag)
                prior_ids = frozenset(set(prior_ids or ()) | set(n_bag))
                tags.append("neighbor-narrow")
            if neighbor_title_ids:
                preferred |= set(neighbor_title_ids)
                tags.append("neighbor-title")
            if neighbor_topic_ids:
                preferred |= set(neighbor_topic_ids)
                tags.append("topic-remap")

        # Exact / near-exact Section title ↔ CRE.name (umbrella latch).
        if self._exact_names is not None:
            exact_ids = self._exact_names.match_for_text(text)
            if exact_ids:
                preferred |= set(exact_ids)
                prior_ids = frozenset(set(prior_ids or ()) | preferred)
                tags.append("exact-name")

        # Same-standard predecessor edition (dynamic remap, cached).
        if self._edition is not None:
            edition_ids_ordered = sorted(self._edition_cre_ids(text))
            if edition_ids_ordered:
                preferred |= set(edition_ids_ordered)
                prior_ids = frozenset(set(prior_ids or ()) | preferred)
                tags.append("edition-reseed")

        # Control-name overlap; boost hits that sit in the full neighbor bag.
        if self._control_names is not None:
            name_ids_ordered = self._control_names.seed_for_text(text)
            if name_ids_ordered:
                if full_neighbor_bag:
                    boosted = [c for c in name_ids_ordered if c in full_neighbor_bag]
                    rest = [c for c in name_ids_ordered if c not in full_neighbor_bag]
                    name_ids_ordered = (boosted + rest)[:12]
                # Only pull control-name into the *narrow* cage (not unbounded).
                name_narrow = name_ids_ordered[:8]
                preferred |= set(name_narrow)
                prior_ids = frozenset(set(prior_ids or ()) | set(name_narrow))
                tags.append("control-name")

        self.last_preferred_cre_ids = merge_preferred(
            link_ids_ordered,
            exact_ids,
            neighbor_title_ids,
            neighbor_topic_ids,
            edition_ids_ordered,
            name_ids_ordered,
            limit=12,
        )

        global_audit = self._retrieve_global(text)
        if not prior_ids:
            audit = global_audit
            tag = f"{problem.class_id}:{problem.family}+soft/uncaged"
        else:
            caged = self._retrieve_allowlist(text, prior_ids)
            tag = f"{problem.class_id}:{problem.family}"
            if tags:
                tag = f"{tag}+{'+'.join(tags)}"
            if not caged.candidates:
                relaxed = self._relaxed_prior(problem)
                if relaxed and relaxed != prior_ids:
                    caged = self._retrieve_allowlist(text, relaxed)
                    prior_ids = frozenset(set(prior_ids) | set(relaxed))
                    tag = f"{tag}+relaxed"

            if (
                self._edition is not None
                and len(caged.candidates) <= self._edition.low_result_max
            ):
                base = frozenset(prior_ids) | self._relaxed_prior(problem)
                expanded = self._edition.expand_allowlist_if_low(
                    text, base, candidate_count=len(caged.candidates)
                )
                if expanded and len(expanded) > len(base):
                    reseeds = self._retrieve_allowlist(text, frozenset(expanded))
                    if len(reseeds.candidates) >= len(caged.candidates):
                        caged = reseeds
                        prior_ids = frozenset(expanded)
                        tag = f"{tag}+edition-retry"

            merged = self._merge_soft(
                caged, global_audit, prior_ids=prior_ids, preferred=preferred
            )
            # A: parents that cover ≥2 shortlist children lead preferred.
            if self._parents is not None and merged:
                parents = self._parents.promote_for_shortlist(
                    [c.cre_id for c in merged[:20]]
                )
                if parents:
                    preferred |= set(parents)
                    self.last_preferred_cre_ids = merge_preferred(
                        parents, self.last_preferred_cre_ids, limit=12
                    )
                    tag = f"{tag}+umbrella"
                    # Pull parent vectors into the shortlist when missing.
                    have = {c.cre_id for c in merged}
                    missing = [p for p in parents if p not in have]
                    if missing:
                        parent_hits = self._retrieve_allowlist(text, frozenset(missing))
                        if parent_hits.candidates:
                            merged = self._merge_soft(
                                parent_hits,
                                global_audit.model_copy(update={"candidates": merged}),
                                prior_ids=prior_ids,
                                preferred=preferred,
                            )
                    else:
                        merged = self._merge_soft(
                            caged,
                            global_audit.model_copy(update={"candidates": merged}),
                            prior_ids=prior_ids,
                            preferred=preferred,
                        )
            audit = global_audit.model_copy(update={"candidates": merged})
            tag = f"{tag}+soft"

        return audit.model_copy(
            update={
                "retriever": (
                    f"{audit.retriever}+prior-cage/{tag}"
                    + (
                        ":empty"
                        if not audit.candidates
                        else f":{len(audit.candidates)}"
                    )
                ),
            }
        )


__all__ = ["PriorCagedRetriever"]
