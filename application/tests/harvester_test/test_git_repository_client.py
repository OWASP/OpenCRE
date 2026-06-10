from application.utils.harvester.git_repository_client import (
    GitRepositoryClient,
)


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

    assert str(client.get_local_path()) == ".harvester_cache/owasp/asvs"


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
