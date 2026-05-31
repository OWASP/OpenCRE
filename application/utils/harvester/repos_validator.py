# as the name suggests
from application.utils.harvester.schemas import ReposFile


class RepositoryValidationError(Exception):
    """Raised when repository configuration fails semantic validation."""


def validate_repositories(config: ReposFile) -> None:
    seen_ids: set[str] = set()
    seen_repositories: set[tuple[str, str]] = set()

    for repository in config.repositories:
        repo_id_key = repository.id.casefold()
        if repo_id_key in seen_ids:
            raise RepositoryValidationError(
                f"Duplicate repository id found: {repository.id}"
            )
        seen_ids.add(repo_id_key)
        repository_key = (
            repository.owner.casefold(),
            repository.repo.casefold(),
        )
        if repository_key in seen_repositories:
            raise RepositoryValidationError(
                f"Duplicate repository detected: {repository.owner}/{repository.repo}"
            )
        seen_repositories.add(repository_key)
        include_patterns = set(repository.paths.include)
        if len(include_patterns) != len(repository.paths.include):
            raise RepositoryValidationError(
                f"Repository '{repository.id}' has duplicate include paths"
            )
