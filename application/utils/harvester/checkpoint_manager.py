from datetime import datetime

from .models import CheckpointRecord


class CheckpointManager:
    """
    Stores pipeline checkpoints for incremental processing.
    """

    def __init__(self):
        self._checkpoints: dict[str, CheckpointRecord] = {}

    def save(self, checkpoint: CheckpointRecord) -> None:
        self._checkpoints[checkpoint.repository] = checkpoint

    def get(self, repository: str) -> CheckpointRecord | None:
        return self._checkpoints.get(repository)

    def update_commit(self, repository: str, commit_sha: str) -> None:
        checkpoint = self._checkpoints.get(repository)

        if checkpoint is None:
            return

        checkpoint.last_processed_commit = commit_sha
        checkpoint.updated_at = datetime.now()

    def mark_completed(self, repository: str) -> None:
        checkpoint = self._checkpoints.get(repository)

        if checkpoint is None:
            return

        checkpoint.status = "completed"
        checkpoint.updated_at = datetime.now()
