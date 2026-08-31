from datetime import datetime
from .models import ArtifactRegistryRecord


class ArtifactRegistry:
    """
    In-memory registry for artifact deduplication.
    """

    def __init__(self):
        self._records: dict[str, ArtifactRegistryRecord] = {}

    def get(self, artifact_id: str) -> ArtifactRegistryRecord | None:
        return self._records.get(artifact_id)

    def exists(self, artifact_id: str) -> bool:
        return artifact_id in self._records

    def upsert(self, record: ArtifactRegistryRecord) -> None:
        record.last_processed_at = datetime.now()
        self._records[record.artifact_id] = record

    def all(self) -> list[ArtifactRegistryRecord]:
        return list(self._records.values())
