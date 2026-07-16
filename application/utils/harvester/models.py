from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


@dataclass(slots=True)
class RepositoryCheckpoint:
    repository_id: str
    last_processed_commit: str | None
    updated_at: datetime
    provider: str
    owner: str
    repository: str
    branch: str


@dataclass(slots=True)
class RepositoryChangeSet:
    repository_id: str
    commit_sha: str
    modified_files: list[str]


class FilteringMetrics(BaseModel):
    total_files: int
    retained_files: int
    filtered_files: int


@dataclass(slots=True)
class DiffBlock:
    """
    Intermediate representation of normalized additions
    extracted from a repository diff.
    """

    file_path: str
    added_lines: list[str]
    repository: str
    commit_sha: str
    committed_at: datetime | None = None


@dataclass(slots=True)
class SourceInfo:
    type: str
    repository: str
    commit_sha: str
    committed_at: datetime | None


@dataclass(slots=True)
class Locator:
    kind: str
    id: str
    path: str


@dataclass(slots=True)
class SpanInfo:
    heading_path: list[str]
    start_line: int
    end_line: int
    index: int | None = None
    total: int | None = None
    start_char_idx: int | None = None
    end_char_idx: int | None = None


@dataclass(slots=True)
class HeadingNode:
    level: int
    text: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class Document:
    schema_version: str
    artifact_id: str
    pipeline_run_id: str
    text: str
    source: SourceInfo
    locator: Locator
    heading_structure: list[HeadingNode]
    span: SpanInfo | None = None


@dataclass(slots=True)
class ArtifactRegistryRecord:
    """
    Tracks the processing state of an artifact.
    Used for deduplication across pipeline runs.
    """

    artifact_id: str
    repository: str
    locator_path: str
    content_hash: str
    last_commit_sha: str
    last_pipeline_run: str
    last_processed_at: datetime
    status: str


class DeduplicationStatus(str, Enum):
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
