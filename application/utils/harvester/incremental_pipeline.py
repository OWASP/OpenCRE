from datetime import datetime, timezone
from typing import Any

from .artifact_registry import ArtifactRegistry
from .checkpoint_store import CheckpointStore
from .deduplication_metrics import DeduplicationMetrics
from .document_deduplicator import DocumentDeduplicator
from .document_validator import DocumentValidator
from .models import (
    DeduplicationStatus,
    Document,
    RepositoryCheckpoint,
)


class IncrementalPipeline:
    """
    Coordinates document validation, deduplication, and durable checkpoints.

    Only NEW or UPDATED validated documents are emitted downstream.
    Checkpoints are written via ``CheckpointStore`` (Postgres/SQLite).
    """

    def __init__(
        self,
        deduplicator: DocumentDeduplicator | None = None,
        checkpoint_store: CheckpointStore | None = None,
        validator: DocumentValidator | None = None,
        *,
        provider: str = "github",
        owner: str = "",
        repository_name: str = "",
        branch: str = "main",
        repository_id: str = "",
    ) -> None:
        self._deduplicator = deduplicator or DocumentDeduplicator(ArtifactRegistry())
        self._checkpoint_store = checkpoint_store or CheckpointStore()
        self._validator = validator or DocumentValidator()
        self.metrics = DeduplicationMetrics()
        self._provider = provider
        self._owner = owner
        self._repository_name = repository_name
        self._branch = branch
        self._repository_id = repository_id

    def process(
        self,
        repository: str,
        pipeline_run_id: str,
        documents: list[Document],
        *,
        last_processed_commit: str | None = None,
    ) -> list[Document]:
        emitted: list[Document] = []
        metrics = DeduplicationMetrics()

        for document in documents:
            if document.pipeline_run_id != pipeline_run_id:
                raise ValueError(
                    f"document pipeline_run_id {document.pipeline_run_id!r} "
                    f"does not match process run {pipeline_run_id!r}"
                )
            if document.source.repository != repository:
                raise ValueError(
                    f"document source.repository {document.source.repository!r} "
                    f"does not match process repository {repository!r}"
                )
            if not self._validator.validate(document):
                raise ValueError(f"document failed validation: {document.artifact_id}")

            status = self._deduplicator.process(document)
            metrics.record(status)
            if status != DeduplicationStatus.UNCHANGED:
                emitted.append(document)

        commit_sha = last_processed_commit
        if commit_sha is None and documents:
            commit_sha = documents[-1].source.commit_sha
        if commit_sha:
            self._persist_checkpoint(pipeline_run_id, commit_sha)

        self.metrics = metrics
        return emitted

    def _persist_checkpoint(self, pipeline_run_id: str, commit_sha: str) -> None:
        if not commit_sha.strip():
            raise ValueError("refusing to persist empty last_processed_commit")
        repository_id = self._repository_id or f"{self._owner}/{self._repository_name}"
        self._checkpoint_store.save(
            RepositoryCheckpoint(
                repository_id=repository_id,
                last_processed_commit=commit_sha,
                updated_at=datetime.now(timezone.utc),
                provider=self._provider,
                owner=self._owner or repository_id.split("/")[0],
                repository=self._repository_name or repository_id.split("/", 1)[-1],
                branch=self._branch,
            )
        )
