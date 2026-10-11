"""Experimental hard crosswalk cage from hub Standard↔CRE seeds.

Gated by ``CRE_LIBRARIAN_CROSSWALK_CAGE`` (default off). When Module C already
knows preferred CRE ids for a chunk (hub Links via Standard/Section-ID —
``last_preferred_cre_ids``), intersect the retrieval shortlist with that set.
Empty intersection leaves candidates empty so coverage / NO_CANDIDATES paths
fire. Soft prefer (PREF_INJECT) remains when this flag is off.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence, Set

from application.utils.librarian.schemas import CreCandidate, RetrievalAudit

logger = logging.getLogger(__name__)


def crosswalk_cage_enabled() -> bool:
    return os.environ.get("CRE_LIBRARIAN_CROSSWALK_CAGE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def apply_crosswalk_cage(
    retrieved: RetrievalAudit,
    preferred_cre_ids: Sequence[str],
) -> RetrievalAudit:
    """Hard-filter candidates to ``preferred_cre_ids`` when flag on + prefs set."""
    if not crosswalk_cage_enabled():
        return retrieved
    allow: Set[str] = {str(c).strip() for c in preferred_cre_ids if str(c).strip()}
    if not allow:
        return retrieved
    kept: List[CreCandidate] = [
        c
        for c in (retrieved.candidates or [])
        if str(getattr(c, "cre_id", "") or "").strip() in allow
    ]
    if len(kept) == len(retrieved.candidates or []):
        return retrieved
    logger.info(
        "crosswalk cage: %s → %s candidates (allow=%s)",
        len(retrieved.candidates or []),
        len(kept),
        len(allow),
    )
    return retrieved.model_copy(
        update={
            "candidates": kept,
            "retriever": f"{retrieved.retriever}+crosswalk-cage",
        }
    )


def cage_allowlist(preferred_cre_ids: Sequence[str]) -> Optional[Set[str]]:
    """Return allowlist when cage should apply, else None."""
    if not crosswalk_cage_enabled():
        return None
    allow = {str(c).strip() for c in preferred_cre_ids if str(c).strip()}
    return allow or None
