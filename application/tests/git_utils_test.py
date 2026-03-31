import unittest
from unittest.mock import MagicMock, patch

from application.utils.git import createPullRequest


class TestGitUtils(unittest.TestCase):
    @patch("application.utils.git.Github")
    def test_create_pull_request_uses_target_branch(self, mocked_github) -> None:
        github_client = MagicMock()
        repo = MagicMock()
        mocked_github.return_value = github_client
        github_client.get_repo.return_value = repo

        createPullRequest(
            apiToken="token",
            repo="OWASP/OpenCRE",
            title="test-title",
            srcBranch="feature-branch",
            targetBranch="main",
        )

        mocked_github.assert_called_once_with("token")
        github_client.get_repo.assert_called_once_with("OWASP/OpenCRE")
        repo.create_pull.assert_called_once_with(
            title="test-title",
            body="CRE Sync test-title",
            head="feature-branch",
            base="main",
        )

    @patch("application.utils.git.Github")
    def test_create_pull_request_defaults_to_master(self, mocked_github) -> None:
        github_client = MagicMock()
        repo = MagicMock()
        mocked_github.return_value = github_client
        github_client.get_repo.return_value = repo

        createPullRequest(
            apiToken="token",
            repo="OWASP/OpenCRE",
            title="default-target",
            srcBranch="feature-branch",
        )

        repo.create_pull.assert_called_once_with(
            title="default-target",
            body="CRE Sync default-target",
            head="feature-branch",
            base="master",
        )


if __name__ == "__main__":
    unittest.main()
