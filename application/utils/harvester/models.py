from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel


@dataclass(slots=True)
class RepositoryCheckpoint:
    repository_id: str
    last_processed_commit: str | None
    updated_at: datetime


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
