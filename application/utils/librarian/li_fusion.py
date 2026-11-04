"""Optional LlamaIndex fusion wrapper around a Librarian C.1 retriever.

When ``CRE_RAG_PARITY_LI_RETRIEVE`` / ``OWASP_CX_LI_RETRIEVE`` is on and LI is
installed, expands the query lightly and fuses shortlists with public
QueryFusionRetriever RRF. OpenCRE ``decide()`` / τ are unchanged — this only
reshapes the candidate pool.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Protocol

logger = logging.getLogger(__name__)


class _Retriever(Protocol):
    def retrieve(self, text: str) -> Any: ...


def li_librarian_fusion_enabled() -> bool:
    for key in (
        "CRE_RAG_PARITY_LI_RETRIEVE",
        "OWASP_CX_LI_RETRIEVE",
    ):
        v = (os.environ.get(key) or "").strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
    return False


def wrap_retriever(inner: _Retriever) -> _Retriever:
    """Return ``inner`` unchanged when flag off or LI missing."""
    if not li_librarian_fusion_enabled():
        return inner
    try:
        from application.utils.comprehension.li_retrieve import li_available

        if not li_available():
            logger.warning(
                "OWASP_CX_LI_RETRIEVE set but LlamaIndex missing; "
                "librarian retriever unchanged"
            )
            return inner
    except Exception:  # noqa: BLE001
        return inner
    return _LiFusedRetriever(inner)


class _LiFusedRetriever:
    def __init__(self, inner: _Retriever) -> None:
        self._inner = inner

    def retrieve(self, text: str) -> Any:
        from application.utils.comprehension.li_retrieve import (
            fuse_rankings_with_llamaindex,
        )
        from application.utils.librarian.schemas import Candidate

        primary = self._inner.retrieve(text)
        # Light multi-query: original + a "requirements about X" paraphrase.
        alt = f"security requirements about {(text or '').strip()}"
        secondary = self._inner.retrieve(alt) if alt != text else primary

        def _cands(audit: Any) -> List[Candidate]:
            return list(getattr(audit, "candidates", None) or [])

        a, b = _cands(primary), _cands(secondary)
        if not a:
            return primary
        fused = fuse_rankings_with_llamaindex(
            [a, b] if b else [a],
            key=lambda c: str(getattr(c, "cre_id", "") or ""),
        )
        if fused is None:
            return primary
        # Preserve audit type; replace candidates with fused order.
        try:
            return primary.model_copy(update={"candidates": fused})
        except Exception:  # noqa: BLE001
            try:
                primary.candidates = fused  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return primary
            return primary
