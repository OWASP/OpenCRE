import os
from pathlib import Path

CACHE_ROOT = Path(os.getenv("HARVESTER_CACHE_DIR", ".harvester_cache"))


def build_repository_cache_path(
    owner: str,
    repository: str,
    branch: str = "main",
) -> Path:
    return CACHE_ROOT / owner.casefold() / repository.casefold() / branch.casefold()
