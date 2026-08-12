"""Module C.0 — the deterministic input boundary (Week 2).

Validates what enters the Librarian and adapts it into the internal
``Section`` the retrieval pipeline consumes. This layer does **no text
normalization**: the RFC (PR #734) assigns text cleanup to Module A
(normalize + chunk) with Module B's sanitizer on top, so ``text`` is
contractually clean by the time it reaches C. Re-cleaning here would
silently drift C from what A hashed and B classified.

Two entry points, one per upstream shape:

- ``section_from_queue_row`` — Module B's live ``knowledge_queue`` row
  (contract v0.2, table merged in #989). ``chunk_id`` and ``artifact_id``
  are **read straight off the row**: they are Module A's identity, carried
  through B, and C consuming them verbatim is what lets a link join back to
  the artifact it came from.

  Through W7 this function *synthesized* those ids from repo/path/sha, which
  produced strings that matched nothing upstream. W8 removed that: the queue
  row is the identity, and the source/locator shape now follows B's
  ``source_type`` (``github`` carries repo+sha, ``rss`` carries a feed url)
  rather than assuming every row is a GitHub commit.

- ``section_from_knowledge_item`` — the full RFC ``KnowledgeItem``
  envelope (fixtures; B writes the flat queue row in practice).

Volatile / audit-only metadata (``llm_reasoning``, ``filtered_at``,
``pipeline_run_id``, filter stages) is intentionally not carried into
``Section`` — downstream stages must never key a decision on it.

Every rejection is a typed ``SectionValidationError`` subclass; raw
Pydantic ``ValidationError`` never escapes this module.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError

from application.utils.librarian.schemas import (
    KnowledgeItem,
    KnowledgeQueueItem,
    KnowledgeStatus,
    Locator,
    LocatorKind,
    SourceRef,
    SourceType,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)

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


def _validate_or_raise(model_cls: Type[_ModelT], raw: Any) -> _ModelT:
    """Coerce a raw row into ``model_cls``, converting Pydantic's ValidationError
    into a typed MalformedKnowledgeItemError so it never escapes this module."""
    if isinstance(raw, model_cls):
        return raw
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        raise MalformedKnowledgeItemError(str(exc)) from exc


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


def _rfc_or_raise(build: Callable[[], _ModelT]) -> _ModelT:
    """Build an RFC sub-model, converting its Pydantic error to a typed one.

    The row-level validator has already checked the field/`source_type` pairing,
    but the RFC models carry rules of their own that B's column types cannot
    express — ``SourceRef.commit_sha`` requires 7+ characters while Module A's
    contract allows 4, and a ``feed_item`` locator requires a parseable URL. Any
    such row is malformed *for C* and must leave as a SectionValidationError.
    """
    try:
        return build()
    except ValidationError as exc:
        raise MalformedKnowledgeItemError(str(exc)) from exc


def _source_ref(row: KnowledgeQueueItem) -> SourceRef:
    """B's flat source columns -> the RFC source-ref, keyed on ``source_type``.

    ``source_committed_at`` is A's real commit time and is github-only; every
    other source type falls back to ``created_at`` (B's classification time),
    which is the best provenance the row carries.
    """
    committed_at = row.source_committed_at or row.created_at
    if row.source_type == SourceType.github:
        return _rfc_or_raise(
            lambda: SourceRef(
                type=SourceType.github,
                repo=row.source_repo,
                commit_sha=row.source_commit_sha,
                committed_at=committed_at,
            )
        )
    # Validated from a mapping rather than constructed: `url` is an ``AnyUrl``
    # and B stores a plain string, so this routes the coercion (and any failure)
    # through Pydantic, where ``_rfc_or_raise`` can type it.
    return _rfc_or_raise(
        lambda: SourceRef.model_validate(
            {
                "type": row.source_type,
                "url": row.feed_url,
                "committed_at": committed_at,
            }
        )
    )


def _locator(row: KnowledgeQueueItem) -> Locator:
    """B's ``locator_kind``/``locator_path`` -> the RFC locator.

    ``repo_path`` addresses by path; ``url``/``feed_item`` address by URL, where
    the stable identity is the post guid when B carried one.
    """
    if row.locator_kind == LocatorKind.repo_path:
        return _rfc_or_raise(
            lambda: Locator(
                kind=LocatorKind.repo_path,
                id=row.locator_path,
                path=row.locator_path,
            )
        )
    return _rfc_or_raise(
        lambda: Locator.model_validate(
            {
                "kind": row.locator_kind,
                "id": row.post_guid or row.locator_path,
                "url": row.locator_path,
            }
        )
    )


def _title_hint(row: KnowledgeQueueItem) -> Optional[str]:
    """The deepest heading above this chunk, when A recorded one.

    Nothing downstream keys a decision on ``title_hint`` — retrieval reads
    ``text`` — so this is provenance carried forward, not a scoring change.
    """
    headings = row.heading_path()
    return headings[-1] if headings else None


def section_from_queue_row(
    row: Union[KnowledgeQueueItem, Dict[str, Any]],
) -> Section:
    """Validate one knowledge_queue row and adapt it to a Section.

    Raises a SectionValidationError subclass on any rejection.
    """
    row = _validate_or_raise(KnowledgeQueueItem, row)

    if row.llm_label != KNOWLEDGE_LABEL:
        raise NotKnowledgeError(
            f"llm_label={row.llm_label!r}; only {KNOWLEDGE_LABEL!r} rows may be linked"
        )
    _require_text(row.text)

    return Section(
        # A's real identity, carried through B — never synthesized here.
        chunk_id=row.chunk_id,
        artifact_id=row.artifact_id,
        text=row.text,
        title_hint=_title_hint(row),
        language=_DEFAULT_LANGUAGE,
        source=_source_ref(row),
        locator=_locator(row),
    )


def section_from_knowledge_item(
    item: Union[KnowledgeItem, Dict[str, Any]],
) -> Section:
    """Validate one RFC KnowledgeItem envelope and adapt it to a Section.

    Raises a SectionValidationError subclass on any rejection.
    """
    item = _validate_or_raise(KnowledgeItem, item)

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
