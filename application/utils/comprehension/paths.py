"""What a file's path says about its value as evidence (used at ingestion and at ranking time)."""

from __future__ import annotations

import re
from typing import Any, List

# Never useful as an answer source: image/asset folders, vendored or generated code, site scaffolding.
_ASSET_DIRS = re.compile(
    r"(^|/)(images?|img|imgs|screenshots?|icons?|fonts?|media|vendor|third[_-]party|bundle|"
    r"node_modules|_site|_includes|_layouts|dist|build|themes?)/",
    re.IGNORECASE,
)
# Folders that mix real content with assets: only their README/index stubs are noise.
_MIXED_DIRS = re.compile(r"(^|/)(assets|static|public|resources)/", re.IGNORECASE)
_STUB_FILE = re.compile(
    r"(^|/)(readme|index)(\.[a-z-]+)?\.(md|markdown|txt)$", re.IGNORECASE
)

# Real content, but a poor first choice when a current page exists.
_LOW_VALUE = re.compile(
    r"(^|/)(old[-_ ]?versions?|archive[sd]?|historical?|legacy|deprecated|tests?|examples?|samples?|"
    r"templates?|translations?)/|"
    r"(changelog|release[-_ ]?notes?|credits|contributors|authors|security|contributing|"
    r"code[_-]of[_-]conduct)\.(md|markdown|txt)$",
    re.IGNORECASE,
)
LOW_VALUE_FACTOR = 0.93


def is_asset_path(path: str) -> bool:
    """True for files that should not be indexed at all (images' READMEs, vendored gems, ...)."""
    p = path or ""
    if _ASSET_DIRS.search(p):
        return True
    return bool(_MIXED_DIRS.search(p) and _STUB_FILE.search(p))


def is_low_value(path: str) -> bool:
    return bool(_LOW_VALUE.search(path or ""))


def priority(path: str) -> float:
    """Score multiplier for ranking: 1.0 normally, a little less for archives, tests, changelogs."""
    return LOW_VALUE_FACTOR if is_low_value(path) else 1.0


def order_and_cap(urls: List[Any], limit: int) -> List[Any]:
    """Keep order of first use, but low-value paths go last; then at most ``limit`` urls."""
    ranked = sorted(enumerate(urls), key=lambda t: (is_low_value(str(t[1])), t[0]))
    return [u for _, u in ranked][:limit]
