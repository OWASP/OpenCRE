"""Optional hub-then-leaf cage (high risk; default off).

1. Unconstrained retrieve → take top-N hub CREs (parents in Contains, else top-N).
2. Re-retrieve with allowlist = those hubs ∪ their Contains children.
3. Soft-fail open: if the cage is empty, return the unconstrained shortlist.
"""

from __future__ import annotations

from typing import AbstractSet, FrozenSet, List, Optional, Set

from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.librarian.umbrella_promote import ParentIndex

HUB_LEAF_RETRIEVER_NAME = "hub-leaf-cage/0.1.0"
_DEFAULT_TOP_HUBS = 3


class HubLeafCageRetriever:
    """Wrap an inner retriever with a hub→leaf Contains allowlist."""

    def __init__(
        self,
        inner: object,
        parent_index: ParentIndex,
        *,
        top_hubs: int = _DEFAULT_TOP_HUBS,
        enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._parents = parent_index
        self._top_hubs = max(1, top_hubs)
        self._enabled = enabled
        #: Hubs chosen on the last ``retrieve`` (debug / eval).
        self.last_hub_cre_ids: List[str] = []

    def retrieve(
        self, text: str, *, allowlist: Optional[AbstractSet[str]] = None
    ) -> RetrievalAudit:
        if not self._enabled:
            return self._call_inner(text, allowlist=allowlist)
        self.last_hub_cre_ids = []
        global_audit = self._call_inner(text, allowlist=allowlist)
        hubs = self._select_hubs(global_audit.candidates or [])
        if not hubs:
            return global_audit.model_copy(
                update={
                    "retriever": f"{global_audit.retriever}+{HUB_LEAF_RETRIEVER_NAME}:no-hub"
                }
            )
        self.last_hub_cre_ids = list(hubs)
        cage = self._cage_for_hubs(hubs)
        if allowlist is not None:
            cage = frozenset(cage & set(allowlist))
        if not cage:
            return global_audit.model_copy(
                update={
                    "retriever": (
                        f"{global_audit.retriever}+{HUB_LEAF_RETRIEVER_NAME}:empty"
                    )
                }
            )
        caged = self._call_inner(text, allowlist=cage)
        if not caged.candidates:
            return global_audit.model_copy(
                update={
                    "retriever": (
                        f"{global_audit.retriever}+{HUB_LEAF_RETRIEVER_NAME}:miss"
                    )
                }
            )
        return caged.model_copy(
            update={
                "retriever": (
                    f"{caged.retriever}+{HUB_LEAF_RETRIEVER_NAME}"
                    f":{len(hubs)}hubs/{len(cage)}ids"
                )
            }
        )

    def _call_inner(
        self, text: str, *, allowlist: Optional[AbstractSet[str]]
    ) -> RetrievalAudit:
        if allowlist is None:
            return self._inner.retrieve(text)  # type: ignore[attr-defined]
        try:
            return self._inner.retrieve(text, allowlist=allowlist)  # type: ignore[call-arg]
        except TypeError:
            audit = self._inner.retrieve(text)  # type: ignore[attr-defined]
            allowed = set(allowlist)
            filtered = [
                c for c in (audit.candidates or []) if c.cre_id in allowed
            ]
            return audit.model_copy(update={"candidates": filtered})

    def _select_hubs(self, candidates: List[CreCandidate]) -> List[str]:
        """Prefer CREs that are Contains parents; else fall back to top-N."""
        parent_ids = set(self._parents.parent_to_children.keys())
        hubs: List[str] = []
        for candidate in candidates:
            cid = candidate.cre_id
            if cid in parent_ids and cid not in hubs:
                hubs.append(cid)
            if len(hubs) >= self._top_hubs:
                return hubs
        if hubs:
            return hubs
        # No known parents in the shortlist — treat top-N as provisional hubs.
        for candidate in candidates:
            if candidate.cre_id not in hubs:
                hubs.append(candidate.cre_id)
            if len(hubs) >= self._top_hubs:
                break
        return hubs

    def _cage_for_hubs(self, hubs: List[str]) -> FrozenSet[str]:
        ids: Set[str] = set(hubs)
        for hub in hubs:
            ids.update(self._parents.parent_to_children.get(hub, ()))
        return frozenset(ids)


__all__ = ["HUB_LEAF_RETRIEVER_NAME", "HubLeafCageRetriever"]
