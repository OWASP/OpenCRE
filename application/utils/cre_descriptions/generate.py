"""Orchestrate one-shot CRE description proposals (no DB writes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from application.utils.cre_descriptions.grounding import (
    grounding_snippet,
    usable_grounding_leaves,
)
from application.utils.cre_descriptions.prompt import (
    build_description_prompt,
    compute_prompt_hash,
    parse_description_text,
)
from application.utils.cre_descriptions.table import ApprovalRow

LlmFn = Callable[[str, str], str]


@dataclass(frozen=True)
class CreDescriptionInput:
    cre_id: str
    name: str
    existing_description: str = ""
    linked_prose: Sequence[str] = ()
    neighbour_names: Sequence[str] = ()


def should_skip(existing_description: str, force: bool) -> bool:
    """Idempotent skip when a non-empty description already exists."""
    if force:
        return False
    return bool((existing_description or "").strip())


def propose_descriptions(
    records: Sequence[CreDescriptionInput],
    llm_fn: Optional[LlmFn],
    *,
    model: str,
    limit: Optional[int] = None,
    force: bool = False,
    dry_run: bool = False,
) -> List[ApprovalRow]:
    """Build approval rows. Never writes ``cre.description``.

    ``dry_run`` still emits rows (prompt_hash + grounding) but leaves
    ``proposed_description`` empty and does not call ``llm_fn``.
    """
    rows: List[ApprovalRow] = []
    for record in records:
        if should_skip(record.existing_description, force=force):
            continue
        if limit is not None and len(rows) >= limit:
            break
        leaves = usable_grounding_leaves(list(record.linked_prose))
        system, user = build_description_prompt(
            cre_id=record.cre_id,
            name=record.name,
            linked_prose=leaves,
            neighbour_names=list(record.neighbour_names),
        )
        prompt_hash = compute_prompt_hash(system, user)
        snippet = grounding_snippet(leaves, list(record.neighbour_names))
        if dry_run:
            proposed = ""
        else:
            if llm_fn is None:
                raise ValueError("llm_fn is required unless dry_run=True")
            proposed = parse_description_text(llm_fn(system, user))
        rows.append(
            ApprovalRow(
                cre_id=record.cre_id,
                name=record.name,
                proposed_description=proposed,
                grounding_snippet=snippet,
                model=model,
                prompt_hash=prompt_hash,
            )
        )
    return rows
