import os
import re

from pathlib import Path
from urllib.parse import quote

CACHE_ROOT = Path(os.getenv("HARVESTER_CACHE_DIR", ".harvester_cache"))

_VALID_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def build_repository_cache_path(
    owner: str, repository: str, branch: str = "main"
) -> Path:
    if not _VALID_COMPONENT.fullmatch(owner):
        raise ValueError(f"Invalid repository owner: {owner}")

    if not _VALID_COMPONENT.fullmatch(repository):
        raise ValueError(f"Invalid repository name: {repository}")

    if branch in {".", ".."}:
        raise ValueError("Invalid branch name")

    encoded_branch = quote(branch, safe="")
    candidate = CACHE_ROOT / owner.casefold() / repository.casefold() / encoded_branch

    candidate.resolve().relative_to(CACHE_ROOT.resolve())

    return candidate
