"""Pydantic v2 contracts for Module C — aligned to RFC PR #734.

Every RFC envelope below is round-tripped against its canonical JSON Schema in
``schemas_test.py`` (vendored under ``_rfc_schemas/``); any drift breaks the
build, not the next mentor review.

Internal models (``KnowledgeQueueItem``, ``GoldenDatasetRow``) are not part of
the RFC — they mirror Module B's SQL row (master guide §1.2) and the regression
harness golden row, respectively.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"
_SCHEMA_VERSION_RE = re.compile(r"^0\.\d+\.\d+$")


def _require_schema_version(value: str) -> None:
    """Shared envelope check — every RFC envelope pins schema_version to 0.x.y.

    Centralized so the regex and message can't drift across envelopes.
    """
    if not _SCHEMA_VERSION_RE.match(value):
        raise ValueError(r"schema_version must match ^0\.\d+\.\d+$")


# ---------- Enums (RFC) ----------


class KnowledgeStatus(str, Enum):
    accepted = "accepted"
    rejected = "rejected"
    deferred = "deferred"


class SourceType(str, Enum):
    github = "github"
    url = "url"
    rss = "rss"


class LocatorKind(str, Enum):
    repo_path = "repo_path"
    url = "url"
    feed_item = "feed_item"


class FilterStageName(str, Enum):
    regex_path = "regex_path"
    regex_content = "regex_content"
    llm_relevance = "llm_relevance"


class ReasonCode(str, Enum):
    below_threshold = "BELOW_THRESHOLD"
    no_candidates = "NO_CANDIDATES"
    adversarial_flag = "ADVERSARIAL_FLAG"
    update_ambiguous = "UPDATE_AMBIGUOUS"


# ---------- RFC sub-models ----------


class SourceRef(BaseModel):
    """RFC source-ref.json — required `committed_at`; github requires repo+sha."""

    model_config = ConfigDict(extra="forbid")
    type: SourceType
    repo: Optional[str] = None
    url: Optional[AnyUrl] = None
    commit_sha: Optional[str] = Field(default=None, min_length=7)
    commit_message: Optional[str] = None
    committed_at: datetime
    author_login: Optional[str] = None

    @model_validator(mode="after")
    def _conditional_github(self) -> "SourceRef":
        if self.type == SourceType.github and (not self.repo or not self.commit_sha):
            raise ValueError("type=github requires repo and commit_sha")
        return self


class Locator(BaseModel):
    """RFC locator.json — kind drives whether `path` or `url` is required."""

    model_config = ConfigDict(extra="forbid")
    kind: LocatorKind
    id: str = Field(min_length=1)
    path: Optional[str] = None
    url: Optional[AnyUrl] = None
    title: Optional[str] = None

    @model_validator(mode="after")
    def _conditional_kind(self) -> "Locator":
        if self.kind == LocatorKind.repo_path and not self.path:
            raise ValueError("kind=repo_path requires path")
        if self.kind in (LocatorKind.url, LocatorKind.feed_item) and not self.url:
            raise ValueError("kind=url|feed_item requires url")
        return self


class KnowledgeContent(BaseModel):
    """RFC knowledge-item.json#/properties/content."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    title_hint: Optional[str] = None
    keywords: Optional[List[str]] = None
    language: Optional[str] = "en"


class FilterStage(BaseModel):
    """RFC knowledge-item.json#/properties/filter/properties/stages[*]."""

    model_config = ConfigDict(extra="forbid")
    name: FilterStageName
    passed: bool
    reason: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = Field(default=None, ge=0)


class Filter(BaseModel):
    """RFC knowledge-item.json#/properties/filter."""

    model_config = ConfigDict(extra="forbid")
    stages: List[FilterStage] = Field(min_length=1)
    is_security_knowledge: Optional[bool] = None
    security_summary: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class Rejection(BaseModel):
    """RFC knowledge-item.json#/properties/rejection."""

    model_config = ConfigDict(extra="forbid")
    reason_code: str
    reason_message: Optional[str] = None


class CreCandidate(BaseModel):
    """RFC link-proposal.json#/$defs/cre_candidate (shared by candidates+reranked)."""

    model_config = ConfigDict(extra="forbid")
    cre_id: str
    cre_name: Optional[str] = None
    score_vector: Optional[float] = None
    score_rerank: Optional[float] = None
    score_hybrid: Optional[float] = None


class RetrievalAudit(BaseModel):
    """RFC link-proposal.json#/$defs/retrieval_audit."""

    model_config = ConfigDict(extra="forbid")
    retriever: str
    candidates: List[CreCandidate]
    reranked: List[CreCandidate]
    threshold: float = Field(ge=0, le=1)


class ProposedLink(BaseModel):
    """RFC proposed-link.json — used by both LinkProposal.links and ReviewItem.suggested_links."""

    model_config = ConfigDict(extra="forbid")
    cre_id: str = Field(min_length=1)
    link_type: str
    confidence: float = Field(ge=0, le=1)
    rationale: Optional[str] = None


class KnowledgeSnapshot(BaseModel):
    """RFC link-proposal.json#/$defs/knowledge_snapshot (shared with ReviewItem)."""

    model_config = ConfigDict(extra="forbid")
    text: str
    source: SourceRef
    locator: Locator
    security_summary: Optional[str] = None


class UpdateDetection(BaseModel):
    """RFC link-proposal.json#/$defs/update_detection."""

    model_config = ConfigDict(extra="forbid")
    is_update: bool
    prior_chunk_id: Optional[str] = None
    prior_document_ref: Optional[str] = None
    adversarial_flags: Optional[List[str]] = None


# ---------- RFC envelopes ----------


class KnowledgeItem(BaseModel):
    """RFC knowledge-item.json — B's full output envelope to C.

    `status=accepted` requires `content`; `status=rejected` requires `rejection`.
    """

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    chunk_id: str
    artifact_id: str
    event_id: str
    pipeline_run_id: str
    filtered_at: datetime
    status: KnowledgeStatus
    source: SourceRef
    locator: Locator
    content: Optional[KnowledgeContent] = None
    filter: Filter
    rejection: Optional[Rejection] = None

    @model_validator(mode="after")
    def _rfc_rules(self) -> "KnowledgeItem":
        _require_schema_version(self.schema_version)
        if self.status == KnowledgeStatus.accepted and self.content is None:
            raise ValueError("status=accepted requires content")
        if self.status == KnowledgeStatus.rejected and self.rejection is None:
            raise ValueError("status=rejected requires rejection")
        return self


class LinkProposal(BaseModel):
    """RFC link-proposal.json — C's auto-link output, status='linked'."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    chunk_id: str
    artifact_id: str
    pipeline_run_id: str
    classified_at: datetime
    status: Literal["linked"] = "linked"
    knowledge: KnowledgeSnapshot
    retrieval: RetrievalAudit
    links: List[ProposedLink] = Field(min_length=1)
    update_detection: UpdateDetection

    @model_validator(mode="after")
    def _schema_version_pattern(self) -> "LinkProposal":
        _require_schema_version(self.schema_version)
        return self


class ReviewItem(BaseModel):
    """RFC review-item.json — C's human-review output, status='review_required'."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    review_id: str
    chunk_id: str
    artifact_id: str
    pipeline_run_id: str
    created_at: datetime
    status: Literal["review_required"] = "review_required"
    reason_code: ReasonCode
    knowledge: KnowledgeSnapshot
    retrieval: RetrievalAudit
    suggested_links: Optional[List[ProposedLink]] = None
    update_detection: UpdateDetection

    @model_validator(mode="after")
    def _schema_version_pattern(self) -> "ReviewItem":
        _require_schema_version(self.schema_version)
        return self


# ---------- Internal (NOT RFC) ----------


class KnowledgeQueueItem(BaseModel):
    """Read-side mirror of Module B's `knowledge_queue` row — contract v0.2.

    Mirrors `application.database.db.KnowledgeQueueItem` (the SQLAlchemy model B
    merged in #989) column for column, including its nullability: `source_repo`
    and `source_commit_sha` are NULL on every `rss` row, so neither may be
    required here. `from_attributes` lets a SQLAlchemy row validate directly.

    `chunk_id` / `artifact_id` are Module A's real identity, carried through B.
    C consumes them verbatim — it must never mint its own, or the graph ends up
    keyed on ids that never join back to A's artifacts.

    Not a wire contract: `extra="ignore"` so B can add columns without breaking C.
    See docs/gsoc_2026_module_b/module_c_contract.md.
    """

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: str
    content_hash: str  # B's dedup key
    # Provenance / traceability — Module A's v0.3 record, passed through by B.
    chunk_id: str
    artifact_id: str
    pipeline_run_id: str
    schema_version: str
    # Source. Which of these are populated is a function of `source_type`;
    # see the `_source_fields_match_type` validator below.
    source_type: SourceType
    source_repo: Optional[str] = None
    source_commit_sha: Optional[str] = None
    source_committed_at: Optional[datetime] = None
    feed_url: Optional[str] = None
    post_guid: Optional[str] = None
    # Locator + position of this chunk within its artifact.
    locator_kind: LocatorKind
    locator_path: str
    span_index: int = Field(ge=0)
    span_total: int = Field(ge=1)
    span_heading_path: Optional[str] = None  # JSON-encoded list[str]
    # Payload + B's verdict.
    text: str
    llm_label: str
    confidence: float = Field(ge=0, le=1)
    llm_reasoning: Optional[str] = None
    created_at: datetime
    consumed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _source_fields_match_type(self) -> "KnowledgeQueueItem":
        """Reject a row whose populated source fields contradict `source_type`.

        Checked here rather than in the adapter so the failure surfaces as one
        typed boundary rejection: the adapter builds an RFC `SourceRef`, whose
        own github rule would otherwise raise a raw Pydantic error from outside
        the validation call.
        """
        if self.source_type == SourceType.github and not (
            self.source_repo and self.source_commit_sha
        ):
            raise ValueError(
                "source_type='github' requires source_repo and source_commit_sha"
            )
        if self.source_type == SourceType.rss and not self.feed_url:
            raise ValueError("source_type='rss' requires feed_url")
        return self

    def heading_path(self) -> List[str]:
        """`span_heading_path` decoded; empty when absent or not decodable.

        B stores A's heading list as a JSON string. A malformed value is a
        cosmetic loss (it only feeds `title_hint`), so it degrades to empty
        rather than rejecting a row that is otherwise linkable.
        """
        if not self.span_heading_path:
            return []
        try:
            decoded = json.loads(self.span_heading_path)
        except (ValueError, TypeError):
            return []
        if not isinstance(decoded, list):
            return []
        return [str(part) for part in decoded if str(part).strip()]


# ---------- Golden dataset (internal, harness only) ----------


class Slice(str, Enum):
    explicit = "explicit"
    positive = "positive"
    hard_negative = "hard_negative"
    update = "update"
    ambiguous = "ambiguous"


class Decision(str, Enum):
    linked = "linked"
    review = "review"


class SourceStandard(str, Enum):
    asvs = "ASVS"
    wstg = "WSTG"
    nist_800_53 = "NIST_800_53"
    pci_dss = "PCI_DSS"
    owasp_cheatsheet = "OWASP_CHEATSHEET"
    other = "OTHER"


class GoldenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    title_hint: Optional[str] = None
    explicit_cre_ref: Optional[str] = None
    prior_text: Optional[str] = None
    source_standard: Optional[SourceStandard] = None


class GoldenExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Decision
    cre_ids: Optional[List[str]] = None
    reason_code: Optional[ReasonCode] = None
    is_update: Optional[bool] = None


class GoldenProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    standard_version: Optional[str] = None
    section_path: Optional[str] = None
    ground_truth_source: str


class GoldenDatasetRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    schema_version: str
    slice: Slice
    input: GoldenInput
    expected: GoldenExpected
    provenance: GoldenProvenance
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _conditional_requirements(self) -> "GoldenDatasetRow":
        if self.slice == Slice.explicit and not self.input.explicit_cre_ref:
            raise ValueError("slice=explicit requires input.explicit_cre_ref")
        if self.slice == Slice.update:
            if not self.input.prior_text:
                raise ValueError("slice=update requires input.prior_text")
            if self.expected.is_update is None:
                raise ValueError("slice=update requires expected.is_update")
        if self.expected.decision == Decision.review and not self.expected.reason_code:
            raise ValueError("decision=review requires expected.reason_code")
        if self.expected.decision == Decision.linked and not self.expected.cre_ids:
            raise ValueError("decision=linked requires expected.cre_ids")
        return self
