"""Seed C.1 prior/preferred from hub Links on LLM Top10 + AI Exchange.

Thin compatibility wrapper over :mod:`standard_link_seed`. Prefer importing
``StandardLinkIndex`` / ``build_standard_link_index`` for new code.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Mapping, Tuple

from application.utils.librarian.problem_class import ProblemClass
from application.utils.librarian.standard_link_seed import (
    EditionLinkMap,
    StandardLinkIndex,
    build_standard_link_index,
    hub_external_ids_by_section,
    normalize_llm_section_id,
    normalize_section_id,
    section_id_from_text,
)


def is_ai_or_llm_chunk(problem: ProblemClass, text: str = "") -> bool:
    """True when taxonomy says AI family or the chunk carries an LLM section id."""
    if problem.family == "ai":
        return True
    sid = (problem.section_id or "").upper()
    if normalize_llm_section_id(sid) or sid.startswith("LLM"):
        return True
    return bool(normalize_llm_section_id(section_id_from_text(text)))


class AixLlmLinkIndex:
    """Hub Link index: LLM Top10 by section + AI Exchange bag (CRE UUIDs)."""

    def __init__(
        self,
        section_to_cres: Mapping[str, Tuple[str, ...]] | None = None,
        aix_cre_ids: FrozenSet[str] | None = None,
        *,
        inner: StandardLinkIndex | None = None,
    ) -> None:
        if inner is not None:
            self._inner = inner
            return
        self._inner = StandardLinkIndex(
            editions={
                "llm_top10": (
                    EditionLinkMap(
                        year=0,
                        section_to_cres=dict(section_to_cres or {}),
                    ),
                )
            },
            bags={"ai_exchange": aix_cre_ids or frozenset()},
        )

    @classmethod
    def empty(cls) -> "AixLlmLinkIndex":
        return cls(inner=StandardLinkIndex.empty())

    @property
    def section_to_cres(self) -> Mapping[str, Tuple[str, ...]]:
        return self._inner.section_maps.get("llm_top10", {})

    @property
    def aix_cre_ids(self) -> FrozenSet[str]:
        return self._inner.bags.get("ai_exchange", frozenset())

    def preferred_for(self, problem: ProblemClass, text: str = "") -> List[str]:
        return self._inner.preferred_for(problem, text)

    def prior_extra_for(self, problem: ProblemClass, text: str = "") -> FrozenSet[str]:
        return self._inner.prior_extra_for(problem, text)


def build_aix_llm_link_index(session: Any) -> AixLlmLinkIndex:
    """Load LLM Top10 section→CRE and AI Exchange CRE bags from ``cre_node_links``."""
    return AixLlmLinkIndex(inner=build_standard_link_index(session))


def hub_llm_external_ids_by_section(session: Any) -> Dict[str, List[str]]:
    """``LLM01`` → distinct ``CRE.external_id`` from Top10-for-LLM Links (gold rebuild)."""
    return hub_external_ids_by_section(session, catalog_key="llm_top10")


__all__ = [
    "AixLlmLinkIndex",
    "build_aix_llm_link_index",
    "hub_llm_external_ids_by_section",
    "is_ai_or_llm_chunk",
    "normalize_llm_section_id",
    "normalize_section_id",
    "section_id_from_text",
]
