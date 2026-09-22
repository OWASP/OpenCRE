"""Module C.0.6 — CRE prior from existing graph links + OIE metadata.

Given a ``ProblemClass``, return the set of hub CRE ids that already look like
the right *checklist* — built from:

- ``cre.document_metadata.oie`` (classes / families / transfers — preferred)
- legacy ``oie_families`` flat list
- sibling-standard transfer buckets from CRE ``oie.transfers`` (and signals)
- optional ``TaxonomyIndex`` for related-class + family→transfer expansion

Retrieval (C.1) is then caged to this prior so ranking happens inside the
problem class, not across the whole hub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from application.utils.librarian.oie_taxonomy import (
    THIN_CLASS_THRESHOLD,
    THIN_TRANSFER_THRESHOLD,
    TaxonomyIndex,
    get_default_taxonomy_index,
    oie_block,
)
from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.schemas import CreCandidate


@dataclass(frozen=True)
class CrePriorIndex:
    """Lookup of prior CRE hub ids by problem class, family, and transfer."""

    class_to_cres: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    family_to_cres: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    transfer_to_cres: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    related_classes: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    family_to_transfer: Mapping[str, str] = field(default_factory=dict)
    #: Minimum family size before family-only cages are used.
    min_prior: int = 5
    thin_class: int = THIN_CLASS_THRESHOLD
    thin_transfer: int = THIN_TRANSFER_THRESHOLD

    @classmethod
    def empty(cls) -> "CrePriorIndex":
        return cls()

    def prior_for(self, problem: ProblemClass) -> FrozenSet[str]:
        """CRE hub ids to cage retrieval to (may be empty = no cage).

        Order:
        1. Fine class alone when rich enough
        2. Class ∪ related classes when thin
        3. ∪ sibling-transfer bucket when still thin (brand-new editions)
        4. Family bucket when class/related empty and family is large enough
        """
        by_class = self.class_to_cres.get(problem.class_id, frozenset())
        related: Set[str] = set()
        for peer in self.related_classes.get(problem.class_id, ()):
            related |= set(self.class_to_cres.get(peer, frozenset()))

        if len(by_class) >= self.thin_class:
            return by_class

        expanded: Set[str] = set(by_class) | related
        transfer_key = self.family_to_transfer.get(problem.family)
        if transfer_key and len(expanded) < self.thin_transfer:
            expanded |= set(self.transfer_to_cres.get(transfer_key, frozenset()))

        if expanded:
            return frozenset(expanded)

        by_family = self.family_to_cres.get(problem.family, frozenset())
        if len(by_family) >= self.min_prior:
            return by_family
        return frozenset()


def build_cre_prior_index(
    *,
    cre_rows: Iterable[Any],
    linked_names_by_cre: Optional[Mapping[str, Iterable[str]]] = None,
    taxonomy: Optional[TaxonomyIndex] = None,
    min_prior: int = 5,
) -> CrePriorIndex:
    """Build a prior index from CRE ORM rows (+ optional linked node names).

    ``cre_rows`` items need ``.id``, and optionally ``.name``, ``.description``,
    ``.metadata_json``. Hub keys in the index are ``cre.id`` (UUID) only so they
    match embeddings / CE text maps.

    Related-class and family→transfer maps come from ``taxonomy`` (Node oie).
    Transfer CRE bags come from each CRE's ``oie.transfers`` / ``oie.signals``.
    """
    linked_names_by_cre = linked_names_by_cre or {}
    tax = taxonomy if taxonomy is not None else get_default_taxonomy_index()
    class_map: Dict[str, Set[str]] = {}
    family_map: Dict[str, Set[str]] = {}
    transfer_map: Dict[str, Set[str]] = {}

    def _add(bucket: Dict[str, Set[str]], key: str, *cre_keys: str) -> None:
        if not key:
            return
        slot = bucket.setdefault(key, set())
        for cid in cre_keys:
            if cid:
                slot.add(cid)

    for cre in cre_rows:
        cre_id = getattr(cre, "id", None) or ""
        # Hub embeddings / CE texts are UUID-keyed — prior keys must match.
        keys = (cre_id,) if cre_id else ()
        if not keys:
            continue
        meta = getattr(cre, "metadata_json", None) or {}
        oie = oie_block(meta)

        families = list(oie.get("families") or meta.get("oie_families") or [])
        classes = list(oie.get("classes") or meta.get("oie_classes") or [])
        transfers = list(oie.get("transfers") or [])
        for sig in oie.get("signals") or []:
            s = str(sig)
            if s.startswith("transfer:") and s not in transfers:
                transfers.append(s)

        for fam in families:
            for k in keys:
                _add(family_map, str(fam), k)
        for class_id in classes:
            for k in keys:
                _add(class_map, str(class_id), k)
        for bucket in transfers:
            for k in keys:
                _add(transfer_map, str(bucket), k)

        # Soft family hints from linked Node names when CRE oie has no families.
        if not families:
            linked_list = list(linked_names_by_cre.get(cre_id, []) or [])
            low = " ".join(linked_list).lower()
            if any(x in low for x in ("ccm", "csa", "kubernetes", "k8s")):
                for k in keys:
                    _add(family_map, "cloud", k)
            if any(x in low for x in ("llm", "aisvs", "genai")):
                for k in keys:
                    _add(family_map, "ai", k)
            if any(x in low for x in ("asvs", "cheat sheet", "cheat_sheet")):
                for k in keys:
                    _add(family_map, "appsec", k)
            if "api" in low and "top" in low:
                for k in keys:
                    _add(family_map, "api", k)

    return CrePriorIndex(
        class_to_cres={k: frozenset(v) for k, v in class_map.items()},
        family_to_cres={k: frozenset(v) for k, v in family_map.items()},
        transfer_to_cres={k: frozenset(v) for k, v in transfer_map.items()},
        related_classes=dict(tax.related_classes),
        family_to_transfer=dict(tax.family_to_transfer),
        min_prior=min_prior,
    )


def cage_candidates(
    candidates: Sequence[CreCandidate],
    prior: FrozenSet[str],
) -> List[CreCandidate]:
    """Strict filter: only candidates in ``prior`` (may be empty or &lt; 3).

    Do **not** pad with uncaged hub hits — a thin or empty cage is a signal
    (few good matches, or a CRE coverage gap).
    """
    if not prior:
        return list(candidates)
    return [c for c in candidates if c.cre_id in prior]


__all__ = [
    "CrePriorIndex",
    "build_cre_prior_index",
    "cage_candidates",
]
