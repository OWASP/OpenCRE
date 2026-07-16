from dataclasses import dataclass
from .models import DeduplicationStatus


@dataclass(slots=True)
class DeduplicationMetrics:
    total_artifacts_scanned: int = 0

    artifacts_new: int = 0
    artifacts_updated: int = 0
    artifacts_unchanged: int = 0

    artifacts_emitted: int = 0
    artifacts_skipped: int = 0

    def record(self, status: DeduplicationStatus) -> None:
        self.total_artifacts_scanned += 1

        if status is DeduplicationStatus.NEW:
            self.artifacts_new += 1
            self.artifacts_emitted += 1

        elif status is DeduplicationStatus.UPDATED:
            self.artifacts_updated += 1
            self.artifacts_emitted += 1

        elif status is DeduplicationStatus.UNCHANGED:
            self.artifacts_unchanged += 1
            self.artifacts_skipped += 1
