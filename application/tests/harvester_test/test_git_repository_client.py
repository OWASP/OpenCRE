from application.utils.harvester.git_repository_client import (
    GitRepositoryClient,
)

from unittest.mock import patch


def test_repository_url_generation():
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    assert client.repository_url == "https://github.com/OWASP/ASVS.git"


def test_local_repository_path():
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    assert str(client.get_local_path()) == ".harvester_cache/owasp/asvs/main"


def test_repository_exists_locally_false():
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    assert client.exists_locally() is False


def test_verify_repository_integrity_false():
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    assert client.verify_repository_integrity() is False


def test_sync_clones_when_repository_missing():
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


def test_sync_fetches_when_repository_exists():
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
def test_fetch_runs_git_command(mock_run):
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    client.fetch()

    mock_run.assert_called_once()


@patch("application.utils.harvester.git_repository_client.subprocess.run")
def test_checkout_runs_git_command(mock_run):
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    client.checkout("main")

    mock_run.assert_called_once()


@patch("application.utils.harvester.git_repository_client.subprocess.run")
def test_get_current_commit_sha_runs_git_command(mock_run):
    mock_run.return_value.stdout = "abc123\n"

    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    sha = client.get_current_commit_sha()

    assert sha == "abc123"
    mock_run.assert_called_once()


@patch("application.utils.harvester.git_repository_client.subprocess.run")
def test_clone_runs_git_command(mock_run):
    client = GitRepositoryClient(
        owner="OWASP",
        repository="ASVS",
    )

    with patch.object(
        client,
        "verify_repository_integrity",
        return_value=False,
    ):
        client.clone()

    mock_run.assert_called_once()
