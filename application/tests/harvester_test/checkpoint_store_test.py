import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.models import RepositoryCheckpoint


class CheckpointStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def test_save_and_load_checkpoint(self):
        store = CheckpointStore()
        checkpoint = RepositoryCheckpoint(
            repository_id="owasp-asvs",
            last_processed_commit="abc123",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="owasp",
            repository="asvs",
            branch="main",
        )

        store.save(checkpoint)
        loaded = store.load("owasp-asvs")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.last_processed_commit, "abc123")
        self.assertEqual(loaded.provider, "github")

    def test_update_upsert_and_two_repositories_remain_isolated(self):
        store = CheckpointStore()
        repo_a = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-1",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="main",
        )
        repo_b = RepositoryCheckpoint(
            repository_id="repo-b",
            last_processed_commit="commit-b",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-b",
            branch="main",
        )
        store.save(repo_a)
        store.save(repo_b)

        updated_a = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-2",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="main",
        )
        store.save(updated_a)

        loaded_a = store.load("repo-a")
        loaded_b = store.load("repo-b")

        self.assertIsNotNone(loaded_a)
        self.assertIsNotNone(loaded_b)
        assert loaded_a is not None
        assert loaded_b is not None
        self.assertEqual(loaded_a.last_processed_commit, "commit-2")
        self.assertEqual(loaded_b.last_processed_commit, "commit-b")

    def test_duplicate_canonical_source_identity_rejected(self):
        store = CheckpointStore()
        first = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-1",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="shared",
            branch="main",
        )
        second = RepositoryCheckpoint(
            repository_id="repo-b",
            last_processed_commit="commit-2",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="shared",
            branch="main",
        )

        store.save(first)

        with self.assertRaises(ValueError):
            store.save(second)

    def test_immutable_repository_identity(self):
        store = CheckpointStore()
        first = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-1",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="main",
        )
        store.save(first)

        conflicting = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-2",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="develop",
        )

        with self.assertRaises(ValueError):
            store.save(conflicting)

    def test_null_initial_checkpoint(self):
        store = CheckpointStore()
        checkpoint = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit=None,
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="main",
        )

        store.save(checkpoint)
        loaded = store.load("repo-a")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIsNone(loaded.last_processed_commit)

    def test_transaction_rollback_leaves_previous_checkpoint_intact(self):
        store = CheckpointStore()
        original = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-1",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="main",
        )
        store.save(original)

        conflicting = RepositoryCheckpoint(
            repository_id="repo-a",
            last_processed_commit="commit-2",
            updated_at=datetime.now(timezone.utc),
            provider="github",
            owner="sample",
            repository="repo-a",
            branch="develop",
        )

        with self.assertRaises(ValueError):
            store.save(conflicting)

        loaded = store.load("repo-a")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.last_processed_commit, "commit-1")

    def test_load_missing_repository(self):
        store = CheckpointStore()
        self.assertIsNone(store.load("repo-b"))


if __name__ == "__main__":
    unittest.main()
