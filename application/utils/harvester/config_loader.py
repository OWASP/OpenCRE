from pathlib import Path
import yaml
from pydantic import ValidationError
from .schemas import ReposFile


class ConfigLoaderError(Exception):
    # when repo config loading fails
    pass


def load_repo_config(path: str | Path) -> ReposFile:
    config_path = Path(path)

    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigLoaderError(f"Invalid YAML syntax in {config_path}") from exc

    try:
        return ReposFile.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigLoaderError(
            f"schema validation failed for {config_path} : {exc}"
        ) from exc
