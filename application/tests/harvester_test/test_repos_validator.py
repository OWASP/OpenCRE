from pathlib import Path
import pytest
from application.utils.harvester.config_loader import (
    load_repo_config,
)
from application.utils.harvester.repos_validator import (
    RepositoryValidationError,
    validate_repositories,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_duplicate_repository_ids():
    config_path = FIXTURES_DIR / "duplicate_repo_ids.yaml"

    config = load_repo_config(config_path)

    with pytest.raises(
        RepositoryValidationError,
        match="Duplicate repository id",
    ):
        validate_repositories(config)


def test_duplicate_repositories():
    config_path = FIXTURES_DIR / "duplicate_repositories.yaml"
    config = load_repo_config(config_path)

    with pytest.raises(
        RepositoryValidationError,
        match="Duplicate repository detected",
    ):
        validate_repositories(config)


def test_duplicate_include_paths():
    config_path = FIXTURES_DIR / "duplicate_include_paths.yaml"
    config = load_repo_config(config_path)

    with pytest.raises(
        RepositoryValidationError,
        match="duplicate include paths",
    ):
        validate_repositories(config)


def test_validate_valid_repositories():
    config_path = FIXTURES_DIR / "valid_repos.yaml"

    config = load_repo_config(config_path)

    validate_repositories(config)
