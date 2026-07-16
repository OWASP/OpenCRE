from .artifact_registry import ArtifactRegistry
from .content_hash import generate_content_hash
from .models import (
    ArtifactRegistryRecord,
    DeduplicationStatus,
    Document,
)
from datetime import datetime


class DocumentDeduplicator:
    """
    Performs artifact-level deduplication.

    Documents are classified as:
        - NEW
        - UPDATED
        - UNCHANGED
    """

    def __init__(self, registry: ArtifactRegistry):
        self._registry = registry

    def process(self, document: Document) -> DeduplicationStatus:
        content_hash = generate_content_hash(document.text)

        existing = self._registry.get(document.artifact_id)

        if existing is None:
            self._registry.upsert(
                ArtifactRegistryRecord(
                    artifact_id=document.artifact_id,
                    repository=document.source.repository,
                    locator_path=document.locator.path,
                    content_hash=content_hash,
                    last_commit_sha=document.source.commit_sha,
                    last_pipeline_run=document.pipeline_run_id,
                    last_processed_at=datetime.now(),
                    status=DeduplicationStatus.NEW.value,
                )
            )

            return DeduplicationStatus.NEW

        if existing.content_hash == content_hash:
            existing.status = DeduplicationStatus.UNCHANGED.value

            self._registry.upsert(existing)

            return DeduplicationStatus.UNCHANGED

        existing.content_hash = content_hash
        existing.last_commit_sha = document.source.commit_sha
        existing.last_pipeline_run = document.pipeline_run_id
        existing.status = DeduplicationStatus.UPDATED.value

        self._registry.upsert(existing)

        return DeduplicationStatus.UPDATED
