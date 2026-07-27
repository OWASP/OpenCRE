import subprocess
import tempfile
import unittest
from pathlib import Path
import threading

from application.utils.harvester.git_repository_client import (
    GitRepositoryClient,
)


class IntegrationGitRepositoryClient(GitRepositoryClient):
    def __init__(self, *args, repository_url: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._repository_url = repository_url

    @property
    def repository_url(self) -> str:
        return self._repository_url


def git(*args, cwd=None):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def git_output(*args, cwd=None):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class GitRepositoryClientIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        self.cache = self.root / "cache"

        git("init", "--bare", self.remote)

        git("clone", self.remote, self.work)

        git("config", "user.name", "Test User", cwd=self.work)
        git("config", "user.email", "test@example.com", cwd=self.work)
        git("checkout", "-b", "main", cwd=self.work)

        (self.work / "test.txt").write_text("v1")

        git("add", ".", cwd=self.work)
        git("commit", "-m", "initial", cwd=self.work)
        git("push", "origin", "main", cwd=self.work)

    def tearDown(self):
        self.tempdir.cleanup()

    def create_client(self):
        return IntegrationGitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
            local_path=self.cache,
            repository_url=str(self.remote),
        )

    def test_fetch_updates_worktree_and_commit(self):
        client = self.create_client()

        client.clone()

        sha1 = client.get_current_commit_sha()

        self.assertEqual(
            (client.get_local_path() / "test.txt").read_text(),
            "v1",
        )

        (self.work / "test.txt").write_text("v2")

        git("add", ".", cwd=self.work)
        git("commit", "-m", "update", cwd=self.work)
        git("push", "origin", "main", cwd=self.work)

        expected_sha = git_output(
            "rev-parse",
            "HEAD",
            cwd=self.work,
        )

        client.fetch()

        self.assertEqual(
            client.get_current_commit_sha(),
            expected_sha,
        )

        self.assertNotEqual(
            sha1,
            expected_sha,
        )

        self.assertEqual(
            (client.get_local_path() / "test.txt").read_text(),
            "v2",
        )

    def test_verify_repository_integrity_rejects_fake_git_directory(self):
        fake = self.root / "fake"

        fake.mkdir()
        (fake / ".git").mkdir()

        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
            local_path=fake,
        )

        self.assertFalse(
            client.verify_repository_integrity(),
        )

    def test_verify_repository_integrity_rejects_wrong_origin(self):
        other_remote = self.root / "other.git"

        git("init", "--bare", other_remote)

        client = self.create_client()

        client.clone()

        git(
            "remote",
            "set-url",
            "origin",
            other_remote,
            cwd=client.get_local_path(),
        )

        self.assertFalse(
            client.verify_repository_integrity(),
        )

    def test_verify_repository_integrity_rejects_missing_branch(self):
        client = IntegrationGitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
            branch="dev",
            local_path=self.cache,
            repository_url=str(self.remote),
        )

        git("clone", self.remote, self.cache)

        self.assertFalse(
            client.verify_repository_integrity(),
        )

    def test_sync_serializes_clone_operations(self):
        client1 = self.create_client()
        client2 = self.create_client()

        exceptions = []

        def run_sync(client):
            try:
                client.sync()
            except Exception as exc:
                exceptions.append(exc)

        t1 = threading.Thread(target=run_sync, args=(client1,))
        t2 = threading.Thread(target=run_sync, args=(client2,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        self.assertFalse(exceptions, f"Unexpected exceptions: {exceptions}")

        self.assertTrue(client1.verify_repository_integrity())
        self.assertTrue(client2.verify_repository_integrity())

        self.assertTrue((self.cache / ".git").exists())

        self.assertEqual(
            client1.get_current_commit_sha(),
            client2.get_current_commit_sha(),
        )

        self.assertEqual((self.cache / "test.txt").read_text(), "v1")


if __name__ == "__main__":
    unittest.main()
