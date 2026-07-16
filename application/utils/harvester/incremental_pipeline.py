from datetime import datetime
from .checkpoint_manager import CheckpointManager
from .deduplication_metrics import DeduplicationMetrics
from .document_deduplicator import (
    DeduplicationStatus,
    DocumentDeduplicator,
)
from .models import (
    CheckpointRecord,
    Document,
)


class IncrementalPipeline:
    """
    Coordinates document deduplication and checkpoint updates.

    Only NEW or UPDATED documents are emitted downstream.
    """

    def __init__(
        self, deduplicator: DocumentDeduplicator, checkpoint_manager: CheckpointManager
    ):

        self._deduplicator = deduplicator
        self._checkpoint_manager = checkpoint_manager
        self.metrics = DeduplicationMetrics()

    def process(
        self, repository: str, pipeline_run_id: str, documents: list[Document]
    ) -> list[Document]:

        emitted: list[Document] = []
        metrics = DeduplicationMetrics()

        if documents:
            self._checkpoint_manager.save(
                CheckpointRecord(
                    repository=repository,
                    pipeline_run_id=pipeline_run_id,
                    last_processed_commit="",
                    status="running",
                    updated_at=datetime.now(),
                )
            )

        for document in documents:
            status = self._deduplicator.process(document)

            metrics.record(status)
            self._checkpoint_manager.update_commit(
                repository,
                document.source.commit_sha,
            )

            if status != DeduplicationStatus.UNCHANGED:
                emitted.append(document)

        self._checkpoint_manager.mark_completed(
            repository,
        )

        self.metrics = metrics
        return emitted
