"""Strict auto-concept creation and near-duplicate merge."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import CONCEPT_CATEGORIES, Concept

# Jaccard similarity on token sets; high bar to avoid sprawl.
CREATE_SIMILARITY_MAX = 0.55  # if similar to existing above this → reuse, don't create
MERGE_SIMILARITY_MIN = 0.85


@dataclass
class ConceptAction:
    action: str  # created | reused | skipped | merged
    concept_key: str
    detail: str = ""


def normalize_concept_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s\-]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def concept_key_for(name: str, category: str) -> str:
    base = normalize_concept_name(name).replace(" ", "-")
    cat = category.strip().lower()
    return f"{cat}:{base}"


def token_set(name: str) -> set:
    return {t for t in normalize_concept_name(name).split() if t}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def find_near_concept(
    store: IndexStore, name: str, category: str, threshold: float
) -> Optional[Concept]:
    tokens = token_set(name)
    best: Optional[Concept] = None
    best_score = 0.0
    for concept in store.list_concepts(include_merged=False):
        if concept.category != category:
            continue
        score = jaccard(tokens, token_set(concept.name))
        if score > best_score:
            best_score = score
            best = concept
    if best is not None and best_score >= threshold:
        return best
    return None


def maybe_create_concept(
    store: IndexStore,
    name: str,
    category: str,
    evidence_urls: Optional[Sequence[str]] = None,
    entity_keys: Optional[Sequence[str]] = None,
    description: str = "",
) -> ConceptAction:
    evidence_urls = list(evidence_urls or [])
    entity_keys = list(entity_keys or [])
    if category not in CONCEPT_CATEGORIES:
        return ConceptAction("skipped", "", f"category {category!r} not allowlisted")
    if not evidence_urls and not entity_keys:
        return ConceptAction("skipped", "", "no Nest/GitHub evidence")
    norm = normalize_concept_name(name)
    if not norm or len(norm) < 3:
        return ConceptAction("skipped", "", "name too short after normalization")

    existing = find_near_concept(store, name, category, threshold=CREATE_SIMILARITY_MAX)
    if existing is not None:
        # Attach entity keys onto existing concept
        merged_keys = sorted(set(existing.entity_keys) | set(entity_keys))
        merged_urls = sorted(set(existing.evidence_urls) | set(evidence_urls))
        existing.entity_keys = merged_keys
        existing.evidence_urls = merged_urls
        store.upsert_concept(existing)
        return ConceptAction("reused", existing.key, "near existing concept")

    key = concept_key_for(name, category)
    concept = Concept(
        key=key,
        name=name.strip(),
        category=category,
        description=description,
        evidence_urls=list(evidence_urls),
        entity_keys=list(entity_keys),
        source="auto",
    )
    store.upsert_concept(concept)
    return ConceptAction("created", key, "strict create")


def auto_concepts_from_index(store: IndexStore) -> List[ConceptAction]:
    actions: List[ConceptAction] = []
    for ch in store.prefer_source_entities("chapter"):
        if ch.get("_conflict"):
            continue
        url = ch.get("url") or ""
        actions.append(
            maybe_create_concept(
                store,
                name=str(ch.get("name") or ch.get("key")),
                category="Community",
                evidence_urls=[url] if url else [],
                entity_keys=[f"chapter:{ch.get('key')}"],
                description="OWASP chapter",
            )
        )
    for p in store.prefer_source_entities("project"):
        if p.get("_conflict"):
            continue
        url = p.get("url") or ""
        actions.append(
            maybe_create_concept(
                store,
                name=str(p.get("name") or p.get("key")),
                category="Project",
                evidence_urls=[url] if url else [],
                entity_keys=[f"project:{p.get('key')}"],
                description=(p.get("description") or "")[:300],
            )
        )
    return actions


def merge_near_duplicate_concepts(
    store: IndexStore, threshold: float = MERGE_SIMILARITY_MIN
) -> List[Tuple[str, str, str]]:
    """Merge near-duplicate concepts within the same category. Returns audit triples."""
    concepts = store.list_concepts(include_merged=False)
    merges: List[Tuple[str, str, str]] = []
    # Stable: keep lexicographically smaller key as survivor when names collide hard.
    for i, a in enumerate(concepts):
        if a.merged_into:
            continue
        for b in concepts[i + 1 :]:
            if b.merged_into or a.category != b.category:
                continue
            score = jaccard(token_set(a.name), token_set(b.name))
            if score < threshold:
                continue
            # Prefer the concept with more evidence; tie-break by key.
            a_score = len(a.evidence_urls) + len(a.entity_keys)
            b_score = len(b.evidence_urls) + len(b.entity_keys)
            if a_score > b_score or (a_score == b_score and a.key <= b.key):
                survivor, loser = a, b
            else:
                survivor, loser = b, a
            reason = f"jaccard={score:.2f}"
            # Fold evidence into survivor
            survivor.evidence_urls = sorted(
                set(survivor.evidence_urls) | set(loser.evidence_urls)
            )
            survivor.entity_keys = sorted(
                set(survivor.entity_keys) | set(loser.entity_keys)
            )
            store.upsert_concept(survivor)
            store.mark_concept_merged(loser.key, survivor.key, reason)
            loser.merged_into = survivor.key
            merges.append((loser.key, survivor.key, reason))
    return merges
