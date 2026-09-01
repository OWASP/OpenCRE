import unittest
from datetime import datetime

from application.utils.harvester.checkpoint_manager import CheckpointManager
from application.utils.harvester.models import CheckpointRecord


class CheckpointManagerTests(unittest.TestCase):
    def test_save_checkpoint(self):
        manager = CheckpointManager()

        checkpoint = CheckpointRecord(
            repository="OWASP/ASVS",
            pipeline_run_id="run1",
            last_processed_commit="abc123",
            status="running",
            updated_at=datetime.now(),
        )

        manager.save(checkpoint)

        self.assertIsNotNone(manager.get("OWASP/ASVS"))

    def test_update_commit(self):
        manager = CheckpointManager()

        checkpoint = CheckpointRecord(
            repository="OWASP/ASVS",
            pipeline_run_id="run1",
            last_processed_commit="abc123",
            status="running",
            updated_at=datetime.now(),
        )

        manager.save(checkpoint)

        manager.update_commit(
            "OWASP/ASVS",
            "deadbeef",
        )

        stored = manager.get("OWASP/ASVS")
        assert stored is not None

        self.assertEqual(stored.last_processed_commit, "deadbeef")

    def test_mark_completed(self):
        manager = CheckpointManager()

        checkpoint = CheckpointRecord(
            repository="OWASP/ASVS",
            pipeline_run_id="run1",
            last_processed_commit="abc123",
            status="running",
            updated_at=datetime.now(),
        )

        manager.save(checkpoint)
        manager.mark_completed("OWASP/ASVS")

        stored = manager.get("OWASP/ASVS")
        assert stored is not None

        self.assertEqual(stored.status, "completed")


if __name__ == "__main__":
    unittest.main()
