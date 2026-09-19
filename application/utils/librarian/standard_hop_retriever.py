"""Standard-prose retrieval → graph Links → CRE ids, unioned with CRE cosine.

C.1 historically searched only CRE hub vectors (name stubs). Standard nodes
already carry page-prose embeddings. This wrapper searches that index, hops
``cre_node_links`` to CRE ids, and unions with the inner CRE shortlist.

Eval leak: a Standard hit whose ``embeddings_content`` contains the query
text is dropped (TRACT hub-firewall). Frame-buster / chrome blobs are skipped.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from typing import AbstractSet, Dict, Mapping, Optional, Sequence

from application.utils.librarian.embedding_quality import classify_content
from application.utils.librarian.hub_firewall import HubRep, leaks
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

_HOP_TAG = "std-hop"


def merge_cre_audits(
    inner: RetrievalAudit,
    hopped: RetrievalAudit,
    *,
    tag: str,
) -> RetrievalAudit:
    """Union by cre_id, keeping the higher vector score; sort descending."""
    by_id: Dict[str, CreCandidate] = {}
    for candidate in list(inner.candidates or []) + list(hopped.candidates or []):
        prev = by_id.get(candidate.cre_id)
        if prev is None or float(candidate.score_vector or 0) > float(
            prev.score_vector or 0
        ):
            by_id[candidate.cre_id] = candidate
    merged = sorted(
        by_id.values(),
        key=lambda c: float(c.score_vector or 0.0),
        reverse=True,
    )
    return inner.model_copy(
        update={
            "candidates": merged,
            "retriever": tag,
        }
    )


def _family_allowed(node_name: str, allowed: Optional[Sequence[str]]) -> bool:
    if not allowed:
        return True
    hay = (node_name or "").strip().lower()
    if not hay:
        return False
    for family in allowed:
        needle = family.strip().lower()
        if needle and needle in hay:
            return True
    return False


class StandardHopRetriever:
    """Retriever Protocol adapter: inner CRE retrieve + Standard hop."""

    def __init__(
        self,
        inner: object,
        standard_retriever: object,
        *,
        node_to_cres: Mapping[str, Sequence[str]],
        node_contents: Mapping[str, str],
        node_names: Mapping[str, str],
        allowed_families: Optional[Sequence[str]] = None,
        max_cres_per_hit: int = 4,
        cre_names: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._inner = inner
        self._standard = standard_retriever
        self._node_to_cres = dict(node_to_cres)
        self._node_contents = dict(node_contents)
        self._node_names = dict(node_names)
        self._allowed = tuple(allowed_families or ())
        self._max_cres_per_hit = max(1, int(max_cres_per_hit))
        self._cre_names = dict(cre_names or {})

    def retrieve(
        self, text: str, *, allowlist: Optional[AbstractSet[str]] = None
    ) -> RetrievalAudit:
        retrieve = getattr(self._inner, "retrieve")
        try:
            inner_audit = retrieve(text, allowlist=allowlist)
        except TypeError:
            inner_audit = retrieve(text)
        std_audit = getattr(self._standard, "retrieve")(text)
        hopped: list[CreCandidate] = []
        seen: set[str] = set()
        for hit in std_audit.candidates or []:
            if float(hit.score_vector or 0.0) <= 0.0:
                continue
            node_id = hit.cre_id
            content = self._node_contents.get(node_id, "")
            if classify_content(content) == "junk":
                continue
            if content and leaks(text, [HubRep(node_id, content)]):
                continue
            if not _family_allowed(self._node_names.get(node_id, ""), self._allowed):
                continue
            for cre_id in list(self._node_to_cres.get(node_id, ()))[
                : self._max_cres_per_hit
            ]:
                if not cre_id or cre_id in seen:
                    continue
                seen.add(cre_id)
                hopped.append(
                    CreCandidate(
                        cre_id=cre_id,
                        cre_name=self._cre_names.get(cre_id),
                        score_vector=float(hit.score_vector or 0.0),
                    )
                )

        hop_audit = RetrievalAudit(
            retriever=_HOP_TAG,
            candidates=hopped,
            reranked=[],
            threshold=inner_audit.threshold,
        )
        inner_name = inner_audit.retriever or "cre"
        return merge_cre_audits(inner_audit, hop_audit, tag=f"{inner_name}+{_HOP_TAG}")


__all__ = ["StandardHopRetriever", "merge_cre_audits"]
