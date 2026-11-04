"""Phase 7: ASVS / long-context memory budgets via compression + hard caps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from application.utils.rag_parity.phase4_rerank import RerankHit, contextual_compress


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int
    max_docs: int
    label: str = "default"


# Conservative defaults for ASVS-sized dumps.
ASVS_BUDGET = ContextBudget(max_chars=8000, max_docs=12, label="asvs")
DEFAULT_BUDGET = ContextBudget(max_chars=6000, max_docs=10, label="default")
LONG_CONTEXT_BUDGET = ContextBudget(max_chars=16000, max_docs=24, label="long")


def apply_context_budget(
    hits: Sequence[RerankHit],
    budget: ContextBudget,
) -> List[RerankHit]:
    trimmed = list(hits)[: budget.max_docs]
    return contextual_compress(trimmed, max_chars=budget.max_chars, enabled=True)


def select_budget(kind: str) -> ContextBudget:
    key = (kind or "").strip().lower()
    if key in ("asvs", "asvs5", "owasp_asvs"):
        return ASVS_BUDGET
    if key in ("long", "long_context"):
        return LONG_CONTEXT_BUDGET
    return DEFAULT_BUDGET
