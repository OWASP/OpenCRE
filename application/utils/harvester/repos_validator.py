# as the name suggests
from application.utils.harvester.schemas import ReposFile


class RepositoryValidationError(Exception):
    """Raised when repository configuration fails semantic validation."""


def validate_repositories(config: ReposFile) -> None:
    seen_ids: set[str] = set()
    seen_repositories: set[tuple[str, str]] = set()

    for repository in config.repositories:
        if repository.id in seen_ids:
            raise RepositoryValidationError(
                f"Duplicate repository id found: {repository.id}"
            )
        seen_ids.add(repository.id)
        repository_key = (
            repository.owner,
            repository.repo,
        )
        if repository_key in seen_repositories:
            raise RepositoryValidationError(
                f"Duplicate repository detected: {repository.owner}/{repository.repo}"
            )
        seen_repositories.add(repository_key)
