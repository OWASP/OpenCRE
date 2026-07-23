import unittest
from unittest.mock import patch

import tempfile
from pathlib import Path

from application.utils.harvester.git_repository_client import (
    GitRepositoryClient,
)


class GitRepositoryClientTests(unittest.TestCase):
    def test_repository_url_generation(self):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        self.assertEqual(
            client.repository_url,
            "https://github.com/OWASP/ASVS.git",
        )

    def test_local_repository_path(self):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        self.assertEqual(
            str(client.get_local_path()),
            ".harvester_cache/owasp/asvs/main",
        )

    def test_repository_exists_locally_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = GitRepositoryClient(
                owner="OWASP",
                repository="ASVS",
                local_path=Path(tmpdir) / "repo",
            )

            self.assertFalse(client.exists_locally())

    def test_verify_repository_integrity_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = GitRepositoryClient(
                owner="OWASP",
                repository="ASVS",
                local_path=Path(tmpdir) / "repo",
            )

            self.assertFalse(client.verify_repository_integrity())

    def test_sync_clones_when_repository_missing(self):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        with (
            patch.object(
                client,
                "verify_repository_integrity",
                return_value=False,
            ),
            patch.object(client, "clone") as mock_clone,
        ):
            client.sync()

        mock_clone.assert_called_once()

    def test_sync_fetches_when_repository_exists(self):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        with (
            patch.object(
                client,
                "verify_repository_integrity",
                return_value=True,
            ),
            patch.object(client, "fetch") as mock_fetch,
        ):
            client.sync()

        mock_fetch.assert_called_once()

    @patch("application.utils.harvester.git_repository_client.subprocess.run")
    def test_fetch_runs_git_command(self, mock_run):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        client.fetch()

        self.assertEqual(mock_run.call_count, 2)

    @patch("application.utils.harvester.git_repository_client.subprocess.run")
    def test_checkout_runs_git_command(self, mock_run):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        client.checkout("main")

        mock_run.assert_called_once_with(
            [
                "git",
                "-C",
                str(client.get_local_path()),
                "checkout",
                "main",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

    @patch("application.utils.harvester.git_repository_client.subprocess.run")
    def test_get_current_commit_sha_runs_git_command(self, mock_run):
        mock_run.return_value.stdout = "abc123\n"

        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        sha = client.get_current_commit_sha()

        self.assertEqual(sha, "abc123")
        mock_run.assert_called_once()

    @patch("application.utils.harvester.git_repository_client.subprocess.run")
    def test_clone_runs_git_command(self, mock_run):
        client = GitRepositoryClient(
            owner="OWASP",
            repository="ASVS",
        )

        with (
            patch.object(client, "verify_repository_integrity", return_value=False),
            patch.object(client, "is_valid_repository", return_value=True),
        ):
            client.clone()

        mock_run.assert_called()


if __name__ == "__main__":
    unittest.main()
