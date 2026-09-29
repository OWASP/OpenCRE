"""C.1 dual index: section titles vs CRE names, body vs hidden summaries.

B2 pages are already long (median ~7k chars). Routing on length would send
every Top 10 row to the summary pool — the failure that dropped A01/A07.
Split on metadata header vs narrative instead.
"""

from __future__ import annotations

from typing import AbstractSet, List, Optional

from application.utils.librarian.focus_query import split_retrieval_query
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

DUAL_RETRIEVER_NAME = "dual-index/0.1.0"


class DualIndexRetriever:
    """Header → name-stub retriever; body → summary retriever; union scores."""

    def __init__(
        self,
        name_retriever: object,
        summary_retriever: object,
        *,
        top_k: int,
        threshold: float,
    ) -> None:
        self._names = name_retriever
        self._summaries = summary_retriever
        self._top_k = top_k
        self._threshold = threshold

    def retrieve(
        self, text: str, *, allowlist: Optional[AbstractSet[str]] = None
    ) -> RetrievalAudit:
        header, body = split_retrieval_query(text)
        name_audit: Optional[RetrievalAudit] = None
        summary_audit: Optional[RetrievalAudit] = None
        if header:
            name_audit = self._names.retrieve(header, allowlist=allowlist)  # type: ignore[attr-defined]
        if body:
            summary_audit = self._summaries.retrieve(  # type: ignore[attr-defined]
                body, allowlist=allowlist
            )
        if name_audit is None and summary_audit is None:
            fallback = self._summaries.retrieve(text or "", allowlist=allowlist)  # type: ignore[attr-defined]
            return fallback.model_copy(
                update={"retriever": DUAL_RETRIEVER_NAME, "reranked": []}
            )
        if name_audit is None:
            merged = summary_audit
        elif summary_audit is None:
            merged = name_audit
        else:
            merged = _merge_with_name_quota(
                name_audit, summary_audit, top_k=self._top_k
            )
        assert merged is not None
        candidates = list(merged.candidates or [])[: self._top_k]
        return merged.model_copy(
            update={
                "candidates": candidates,
                "reranked": [],
                "retriever": DUAL_RETRIEVER_NAME,
                "threshold": self._threshold,
            }
        )


def _merge_with_name_quota(
    name_audit: RetrievalAudit,
    summary_audit: RetrievalAudit,
    *,
    top_k: int,
) -> RetrievalAudit:
    """Keep a name-stub slice even when summary cosines are higher.

    The two pools are not score-calibrated. A naive max-score union lets a
    CWE-732 summary blob drown ``Technical application access control``.
    """
    reserve = max(1, top_k // 2)
    names = list(name_audit.candidates or [])[:reserve]
    summary = list(summary_audit.candidates or [])
    best: dict[str, CreCandidate] = {}
    for candidate in names + summary:
        prev = best.get(candidate.cre_id)
        if prev is None or float(candidate.score_vector or 0) > float(
            prev.score_vector or 0
        ):
            best[candidate.cre_id] = candidate
    ordered: List[CreCandidate] = []
    seen: set[str] = set()
    for candidate in names:
        chosen = best[candidate.cre_id]
        if chosen.cre_id in seen:
            continue
        ordered.append(chosen)
        seen.add(chosen.cre_id)
    extras = sorted(
        (c for c in summary if c.cre_id not in seen),
        key=lambda c: float(c.score_vector or 0.0),
        reverse=True,
    )
    for candidate in extras:
        if len(ordered) >= top_k:
            break
        ordered.append(best.get(candidate.cre_id, candidate))
        seen.add(candidate.cre_id)
    return name_audit.model_copy(
        update={
            "candidates": ordered[:top_k],
            "reranked": [],
            "retriever": DUAL_RETRIEVER_NAME,
        }
    )


__all__ = ["DUAL_RETRIEVER_NAME", "DualIndexRetriever"]
