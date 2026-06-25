"""Module C.0 — the deterministic input boundary (Week 2).

Validates what enters the Librarian and adapts it into the internal
``Section`` the retrieval pipeline consumes. This layer does **no text
normalization**: the RFC (PR #734) assigns text cleanup to Module A
(normalize + chunk) with Module B's sanitizer on top, so ``text`` is
contractually clean by the time it reaches C. Re-cleaning here would
silently drift C from what A hashed and B classified.

Two entry points, one per upstream shape:

- ``section_from_queue_row`` — Module B's reduced ``knowledge_queue`` row
  (master guide §1.2). The RFC identity fields C needs downstream are
  synthesized from the row::

      artifact_id = "art:{source_repo}:{source_path}"
      chunk_id    = "chk:{source_repo}@{source_commit_sha}:{source_path}"

  This chunk_id format differs from Module B's ``ChangeRecord``
  (``chk:art:{repo}:{path}:{index}``); align the two when the live
  B->C pipeline wiring lands (W8). Not blocking W2 — no shared consumer yet.

- ``section_from_knowledge_item`` — the full RFC ``KnowledgeItem``
  envelope (fixtures today; the live B->C path lands W8).

Volatile / audit-only metadata (``llm_reasoning``, ``filtered_at``,
``pipeline_run_id``, filter stages) is intentionally not carried into
``Section`` — downstream stages must never key a decision on it.

Every rejection is a typed ``SectionValidationError`` subclass; raw
Pydantic ``ValidationError`` never escapes this module.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from pydantic import ValidationError

from application.utils.librarian.schemas import (
    KnowledgeItem,
    KnowledgeQueueItem,
    KnowledgeStatus,
    Locator,
    LocatorKind,
    SourceRef,
    SourceType,
)

KNOWLEDGE_LABEL = "KNOWLEDGE"

# MVP scope: golden dataset and CRE hub vectors are English-only.
_SUPPORTED_PRIMARY_LANGUAGES = frozenset({"en"})
_DEFAULT_LANGUAGE = "en"


class SectionValidationError(ValueError):
    """Base class for every typed rejection at the C.0 boundary."""


class MalformedKnowledgeItemError(SectionValidationError):
    """Input does not match its contract (wraps Pydantic validation failure)."""


class EmptyTextError(SectionValidationError):
    """Text is empty or whitespace-only — nothing to retrieve against."""


class UnsupportedLanguageError(SectionValidationError):
    """Language is outside the supported set (English-only MVP)."""


class NotKnowledgeError(SectionValidationError):
    """Item was not accepted as security knowledge upstream; C must not link it."""


@dataclass(frozen=True)
class Section:
    """What the C.1+ pipeline consumes: identity + text + provenance, nothing else."""

    chunk_id: str
    artifact_id: str
    text: str
    title_hint: Optional[str]
    language: str
    source: SourceRef
    locator: Locator


def _require_text(text: str) -> str:
    if not text or not text.strip():
        raise EmptyTextError("section text is empty or whitespace-only")
    return text


def _require_language(language: Optional[str]) -> str:
    if language is None:
        return _DEFAULT_LANGUAGE
    primary = language.split("-", 1)[0].lower()
    if primary not in _SUPPORTED_PRIMARY_LANGUAGES:
        raise UnsupportedLanguageError(
            f"unsupported language {language!r}; supported: "
            f"{sorted(_SUPPORTED_PRIMARY_LANGUAGES)}"
        )
    return language


def section_from_queue_row(
    row: Union[KnowledgeQueueItem, Dict[str, Any]],
) -> Section:
    """Validate one knowledge_queue row and adapt it to a Section.

    Raises a SectionValidationError subclass on any rejection.
    """
    if not isinstance(row, KnowledgeQueueItem):
        try:
            row = KnowledgeQueueItem.model_validate(row)
        except ValidationError as exc:
            raise MalformedKnowledgeItemError(str(exc)) from exc

    if row.llm_label != KNOWLEDGE_LABEL:
        raise NotKnowledgeError(
            f"llm_label={row.llm_label!r}; only {KNOWLEDGE_LABEL!r} rows may be linked"
        )
    _require_text(row.text)

    # B's reduced row has no commit timestamp; created_at (B's classification
    # time) is the best available provenance until the live B->C path lands.
    source = SourceRef(
        type=SourceType.github,
        repo=row.source_repo,
        commit_sha=row.source_commit_sha,
        committed_at=row.created_at,
    )
    locator = Locator(
        kind=LocatorKind.repo_path,
        id=row.source_path,
        path=row.source_path,
    )
    return Section(
        chunk_id=f"chk:{row.source_repo}@{row.source_commit_sha}:{row.source_path}",
        artifact_id=f"art:{row.source_repo}:{row.source_path}",
        text=row.text,
        title_hint=None,
        language=_DEFAULT_LANGUAGE,
        source=source,
        locator=locator,
    )


def section_from_knowledge_item(
    item: Union[KnowledgeItem, Dict[str, Any]],
) -> Section:
    """Validate one RFC KnowledgeItem envelope and adapt it to a Section.

    Raises a SectionValidationError subclass on any rejection.
    """
    if not isinstance(item, KnowledgeItem):
        try:
            item = KnowledgeItem.model_validate(item)
        except ValidationError as exc:
            raise MalformedKnowledgeItemError(str(exc)) from exc

    if item.status != KnowledgeStatus.accepted:
        raise NotKnowledgeError(
            f"status={item.status.value!r}; only 'accepted' items may be linked"
        )
    # Keep boundary behavior typed even for pre-built/mutated model instances.
    if item.content is None:
        raise MalformedKnowledgeItemError("status='accepted' requires content")
    _require_text(item.content.text)
    language = _require_language(item.content.language)

    return Section(
        chunk_id=item.chunk_id,
        artifact_id=item.artifact_id,
        text=item.content.text,
        title_hint=item.content.title_hint,
        language=language,
        source=item.source,
        locator=item.locator,
    )
