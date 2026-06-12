from pathlib import Path
import pytest
from application.utils.harvester.config_loader import (
    ConfigLoaderError,
    load_repo_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_load_valid_config():
    config_path = FIXTURES_DIR / "valid_repos.yaml"

    config = load_repo_config(config_path)

    assert len(config.repositories) == 1

    repo = config.repositories[0]

    assert repo.id == "owasp-asvs"
    assert repo.owner == "OWASP"
    assert repo.repo == "ASVS"


def test_missing_repository_id():
    config_path = FIXTURES_DIR / "invalid_missing_id.yaml"
    with pytest.raises(ConfigLoaderError):
        load_repo_config(config_path)


def test_invalid_chunk_size():
    config_path = FIXTURES_DIR / "invalid_chunk_size.yaml"
    with pytest.raises(ConfigLoaderError, match="max_tokens"):
        load_repo_config(config_path)


def test_invalid_yaml_syntax():
    config_path = FIXTURES_DIR / "invalid_yaml.yaml"
    with pytest.raises(ConfigLoaderError):
        load_repo_config(config_path)


def test_missing_config_file():
    with pytest.raises(FileNotFoundError):
        load_repo_config("does_not_exist.yaml")


def test_empty_owner():
    config_path = FIXTURES_DIR / "empty_owner.yaml"

    with pytest.raises(
        ConfigLoaderError,
        match="owner",
    ):
        load_repo_config(config_path)


def test_invalid_chunking_strategy():
    config_path = FIXTURES_DIR / "invalid_chunking_strategy.yaml"

    with pytest.raises(
        ConfigLoaderError,
        match="strategy",
    ):
        load_repo_config(config_path)


def test_invalid_polling_mode():
    config_path = FIXTURES_DIR / "invalid_polling_mode.yaml"

    with pytest.raises(
        ConfigLoaderError,
        match="mode",
    ):
        load_repo_config(config_path)
