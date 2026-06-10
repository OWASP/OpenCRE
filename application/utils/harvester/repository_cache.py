from pathlib import Path

CACHE_ROOT = Path(".harvester_cache")


def build_repository_cache_path(owner: str, repository: str) -> Path:
    return CACHE_ROOT / owner.casefold() / repository.casefold()
