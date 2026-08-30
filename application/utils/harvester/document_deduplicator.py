from datetime import datetime

from .artifact_registry import ArtifactRegistry
from .content_hash import generate_content_hash
from .models import (
    ArtifactRegistryRecord,
    DeduplicationStatus,
    Document,
)


class DocumentDeduplicator:
    """
    Performs artifact-level deduplication within a process.

    Documents are classified as NEW, UPDATED, or UNCHANGED.
    """

    def __init__(self, registry: ArtifactRegistry):
        self._registry = registry

    def process(self, document: Document) -> DeduplicationStatus:
        content_hash = generate_content_hash(document.text)
        existing = self._registry.get(document.artifact_id)
        now = datetime.now()

        if existing is None:
            self._registry.upsert(
                ArtifactRegistryRecord(
                    artifact_id=document.artifact_id,
                    repository=document.source.repository,
                    locator_path=document.locator.path,
                    content_hash=content_hash,
                    last_commit_sha=document.source.commit_sha,
                    last_pipeline_run=document.pipeline_run_id,
                    last_processed_at=now,
                    status=DeduplicationStatus.NEW.value,
                )
            )
            return DeduplicationStatus.NEW

        existing.last_commit_sha = document.source.commit_sha
        existing.last_pipeline_run = document.pipeline_run_id
        existing.last_processed_at = now

        if existing.content_hash == content_hash:
            existing.status = DeduplicationStatus.UNCHANGED.value
            self._registry.upsert(existing)
            return DeduplicationStatus.UNCHANGED

        existing.content_hash = content_hash
        existing.status = DeduplicationStatus.UPDATED.value
        self._registry.upsert(existing)
        return DeduplicationStatus.UPDATED
