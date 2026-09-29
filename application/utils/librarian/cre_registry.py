"""Emit-time CRE membership grounding for Module C.

C.1 already ranks hub embeddings and C.0.5 resolves against ``known_cre_ids``,
but a ghost ``cre_id`` can still reach the emitter (stub seams, map bugs, or a
future stage). This seam is the last check before an envelope leaves the
pipeline: every ProposedLink ``cre_id`` must be a real ``cre`` row (UUID ``id``
or ``external_id``), optionally canonicalised via a map.

Hermetic tests inject a frozenset/map; the live factory builds membership from
the ``cre`` table. ``CreRegistry.disabled()`` is a no-op passthrough so existing
stub pipelines keep working until they opt in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

from application.utils.librarian.decision_engine import DecisionResult
from application.utils.librarian.schemas import Decision, ReasonCode


@dataclass(frozen=True)
class CreRegistry:
    """Lookup of real CRE ids for emit-time grounding.

    ``membership`` is ``None`` when grounding is disabled (passthrough). An empty
    frozenset is active and rejects every id — correct when the ``cre`` table is
    empty in a live build.
    """

    membership: Optional[frozenset[str]]
    canonical_map: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> "CreRegistry":
        return cls(membership=None)

    @classmethod
    def from_membership(
        cls,
        membership: frozenset[str],
        canonical_map: Optional[Mapping[str, str]] = None,
    ) -> "CreRegistry":
        return cls(membership=membership, canonical_map=canonical_map or {})

    @property
    def active(self) -> bool:
        return self.membership is not None

    def resolve(self, cre_id: str) -> Optional[str]:
        """Return the canonical hub id when ``cre_id`` is a known member.

        When grounding is disabled, returns ``cre_id`` unchanged (including empty
        strings) so callers can treat the seam as a pure passthrough.
        """
        if self.membership is None:
            return cre_id
        cid = (cre_id or "").strip()
        if not cid:
            return None
        canonical = self.canonical_map.get(cid, cid)
        if canonical in self.membership:
            return canonical
        if cid in self.membership:
            return cid
        return None

    def ground_ids(self, cre_ids: Sequence[str]) -> Tuple[str, ...]:
        """Keep known ids only, canonicalised, order-preserving, deduped."""
        if self.membership is None:
            return tuple(cre_ids)
        seen: set[str] = set()
        out: list[str] = []
        for cre_id in cre_ids:
            resolved = self.resolve(cre_id)
            if resolved is None or resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
        return tuple(out)


def ground_decision(result: DecisionResult, registry: CreRegistry) -> DecisionResult:
    """Filter ``result.cre_ids`` against membership before emit.

    Linked with zero valid ids becomes review with ``ReasonCode.no_candidates``.
    Review keeps its reason and drops only the invalid suggestions.
    ``gap_proposal`` (CRE_GAP) is preserved — the proposed id is intentionally
    not in the hub yet.
    """
    if not registry.active:
        return result

    if result.gap_proposal is not None:
        return result

    grounded = registry.ground_ids(result.cre_ids)
    if result.decision == Decision.linked:
        if not grounded:
            return DecisionResult(
                Decision.review,
                result.confidence,
                (),
                ReasonCode.no_candidates,
            )
        if grounded == result.cre_ids:
            return result
        return DecisionResult(Decision.linked, result.confidence, grounded, None)

    if grounded == result.cre_ids:
        return result
    return DecisionResult(
        Decision.review,
        result.confidence,
        grounded,
        result.reason_code,
        gap_proposal=result.gap_proposal,
    )


__all__ = ["CreRegistry", "ground_decision"]
