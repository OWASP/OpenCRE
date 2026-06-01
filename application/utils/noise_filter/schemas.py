"""Pydantic v2 models for Module B's data contracts.

Mirrors Module A's actual emission shape (mock confirmed 2026-05-29):
    schema_version, chunk_id, artifact_id, pipeline_run_id, text, span, source, locator

Discriminated union on `source.type` for forward compatibility with RSS feeds
(mock currently only includes github records).

This module is the canonical source for the JSON Schema artifact at
docs/gsoc_2026_module_b/module_a_contract.schema.json -- generate via
`ChangeRecord.model_json_schema()`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# --- Source: discriminated union -----------------------------------------

class GithubSource(BaseModel):
    """github source -- a commit touching a file in an OWASP repo."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: Literal["github"]
    # Lenient regex: allow owner/repo with dots/dashes (OWASP/SAMM-Core etc.).
    repo: str = Field(min_length=3, pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
    # Production: 40-char hex. Mock uses shorter placeholders (e.g. "abc123").
    # We accept any non-empty hex-ish string; strict 40-char enforcement is a
    # production concern, not a schema concern.
    commit_sha: str = Field(min_length=4)
    # ISO-8601 string. Not parsed to datetime here to keep schema purity and
    # avoid Pydantic's strict timestamp parsing breaking on edge formats.
    committed_at: str


class RssSource(BaseModel):
    """rss source -- a post fetched from a feed."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: Literal["rss"]
    feed_url: str = Field(min_length=1)
    post_guid: str = Field(min_length=1)
    post_published_at: Optional[str] = None


Source = Annotated[
    Union[GithubSource, RssSource],
    Field(discriminator="type"),
]


# --- Span: chunk position within its parent artifact ---------------------

class Span(BaseModel):
    """Position of this chunk within the parent artifact.

    `heading_path` is the breadcrumb of markdown headings enclosing the chunk
    (e.g. ["Authentication", "JWT"]). Used by Module B's LLM prompt as a
    semantic context signal -- it replaces Module A v0.2's `commit_message`
    weak signal.
    """

    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    total: int = Field(ge=1)
    heading_path: list[str] = Field(default_factory=list)
    start_char_idx: Optional[int] = Field(default=None, ge=0)
    end_char_idx: Optional[int] = Field(default=None, ge=0)
    start_line: Optional[int] = Field(default=None, ge=0)
    end_line: Optional[int] = Field(default=None, ge=0)


# --- Locator: addressing scheme for the chunk's content ------------------

class Locator(BaseModel):
    """Where this chunk lives addressable-wise.

    `kind` is the scheme: today only "repo_path" is observed (github file at
    a commit); future schemes may include "feed_post" for RSS or others.
    `id` is the unique identity within the scheme; `path` is a convenience
    duplicate for repo_path (id == path in practice).
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    path: str = Field(min_length=1)


# --- Top-level: ChangeRecord (what Module A emits per line in JSONL) ----

class ChangeRecord(BaseModel):
    """One record in Module A's JSONL output stream.

    Required by contract. `extra="ignore"` ensures forward compatibility with
    future Module A field additions (e.g. `supersedes_artifact_id`,
    `pr_number`, etc.) -- B silently passes them through without breaking.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    schema_version: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    pipeline_run_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    span: Span
    source: Source
    locator: Locator


# --- B's internal models -------------------------------------------------

class ClassifyResult(BaseModel):
    """Stage 2 LLM classifier output -- one decision per chunk."""

    model_config = ConfigDict(extra="ignore")

    label: Literal["KNOWLEDGE", "NOISE", "UNCERTAIN"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class QueuePayload(BaseModel):
    """The {source, text, confidence} envelope Module C reads from knowledge_queue.

    The `source` string is composed differently per source.type by the SQL
    CASE in Module C's read query; this model is for typed Python access
    (e.g. logs, JSONL audit, tests) rather than the canonical DB read path.
    """

    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


__all__ = [
    "ChangeRecord",
    "Source",
    "GithubSource",
    "RssSource",
    "Span",
    "Locator",
    "ClassifyResult",
    "QueuePayload",
]
