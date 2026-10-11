"""Shared Postgres-backed cache for librarian LLM JSON responses.

Kinds share one table (``oie_llm_cache``). Disk dirs are opt-in via env for
eval forks; live workers use memory + Postgres only.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

KIND_SHORTLIST_JUDGE = "shortlist_judge"
KIND_EDITION_REMAP = "edition_remap"
KIND_NEIGHBOR_REMAP = "neighbor_remap"
KIND_SAFETY_GUARD = "safety_guard"

# Legacy defaults — only used by migrate script / explicit env opt-in.
LEGACY_DISK = {
    KIND_SHORTLIST_JUDGE: "tmp/oie_shortlist_judge_cache",
    KIND_EDITION_REMAP: "tmp/oie_edition_remap_cache",
    KIND_NEIGHBOR_REMAP: "tmp/oie_neighbor_remap_cache",
}

_ENV_FOR_KIND = {
    KIND_SHORTLIST_JUDGE: "CRE_LIBRARIAN_SHORTLIST_JUDGE_CACHE",
    KIND_EDITION_REMAP: "CRE_LIBRARIAN_EDITION_REMAP_CACHE",
    KIND_NEIGHBOR_REMAP: "CRE_LIBRARIAN_NEIGHBOR_REMAP_CACHE",
}


def optional_disk_dir(kind: str) -> Optional[Path]:
    """Return a disk cache dir only when the kind's env var is set non-empty."""
    env_key = _ENV_FOR_KIND.get(kind)
    if not env_key:
        return None
    raw = (os.environ.get(env_key) or "").strip()
    return Path(raw) if raw else None


def read_json_file(path: Path) -> Optional[Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return data


def write_json_file(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    except OSError:
        logger.debug("LLM cache disk write failed for %s", path, exc_info=True)


__all__ = [
    "KIND_EDITION_REMAP",
    "KIND_NEIGHBOR_REMAP",
    "KIND_SAFETY_GUARD",
    "KIND_SHORTLIST_JUDGE",
    "LEGACY_DISK",
    "optional_disk_dir",
    "read_json_file",
    "write_json_file",
]
