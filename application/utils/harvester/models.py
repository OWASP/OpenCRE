from dataclasses import dataclass
from datetime import datetime


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
