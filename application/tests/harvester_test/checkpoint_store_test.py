import unittest
from datetime import datetime
from pathlib import Path

from application.utils.harvester.checkpoint_store import (
    CheckpointStore,
)
from application.utils.harvester.models import (
    RepositoryCheckpoint,
)


class CheckpointStoreTests(unittest.TestCase):
    def test_save_and_load_checkpoint(self):
        tmp_dir = Path(self._testMethodName)

        try:
            store = CheckpointStore(
                tmp_dir / "checkpoints.json",
            )

            checkpoint = RepositoryCheckpoint(
                repository_id="owasp-asvs",
                last_processed_commit="abc123",
                updated_at=datetime.now(),
            )

            store.save(checkpoint)

            loaded = store.load("owasp-asvs")

            if loaded is None:
                self.fail("Checkpoint should have been loaded")

            self.assertEqual(
                loaded.last_processed_commit,
                "abc123",
            )

        finally:
            if tmp_dir.exists():
                import shutil

                shutil.rmtree(tmp_dir)

    def test_load_missing_file(self):
        tmp_dir = Path(self._testMethodName)

        try:
            store = CheckpointStore(
                tmp_dir / "missing.json",
            )

            self.assertIsNone(
                store.load("repo"),
            )

        finally:
            if tmp_dir.exists():
                import shutil

                shutil.rmtree(tmp_dir)

    def test_load_missing_repository(self):
        tmp_dir = Path(self._testMethodName)

        try:
            store = CheckpointStore(
                tmp_dir / "checkpoint.json",
            )

            store.save(
                RepositoryCheckpoint(
                    repository_id="repo-a",
                    last_processed_commit="abc123",
                    updated_at=datetime.now(),
                )
            )

            self.assertIsNone(
                store.load("repo-b"),
            )

        finally:
            if tmp_dir.exists():
                import shutil

                shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    unittest.main()
