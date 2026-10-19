"""Assemble whole documents from harvested chunks (``harvest_input``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

# Boilerplate that says nothing about the standard itself.
_NOISE_NAMES = re.compile(
    r"(code[_-]?of[_-]?conduct|license|licence|contributing|security\.md|"
    r"pull_request_template|issue_template|changelog|\.github/|/archive/|"
    r"node_modules/|authors|notice|"
    r"(^|/)(es|fr|de|pt|pt-br|it|ja|ko|zh|zh-cn|zh-tw|ru|tr|ar|hi|id|nl|pl|vi|uk)/)",
    re.IGNORECASE,
)


# Raw chunks keep policy/process pages (SECURITY, CONTRIBUTING, CHANGELOG): users ask about them.
_RAW_NOISE = re.compile(
    r"(code[_-]?of[_-]?conduct|licen[cs]e|pull_request_template|issue_template|"
    r"\.github/|/archive/|node_modules/|authors|"
    r"(^|/)(es|fr|de|pt|pt-br|it|ja|ko|zh|zh-cn|zh-tw|ru|tr|ar|hi|id|nl|pl|vi|uk)/)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceDoc:
    repo: str
    artifact_id: str
    path: str
    text: str


def is_noise_path(path: str) -> bool:
    return bool(_NOISE_NAMES.search(path or ""))


def docs_from_rows(rows: Iterable[Tuple[str, str, Dict[str, Any]]]) -> List[SourceDoc]:
    """``rows`` = (source_repo, artifact_id, payload). Chunks are re-ordered by span."""
    grouped: Dict[Tuple[str, str], List[Tuple[int, str, str]]] = {}
    for repo, artifact_id, payload in rows:
        text = str((payload or {}).get("text") or "")
        span = (payload or {}).get("span") or {}
        loc = (payload or {}).get("locator") or {}
        path = str(
            (loc.get("path") if isinstance(loc, dict) else None)
            or str(artifact_id).split(":", 2)[-1]
        )
        grouped.setdefault((repo, artifact_id), []).append(
            (int(span.get("index") or 0), path, text)
        )
    docs: List[SourceDoc] = []
    for (repo, artifact_id), chunks in grouped.items():
        chunks.sort(key=lambda c: c[0])
        path = chunks[0][1]
        if is_noise_path(path):
            continue
        # Chunk text carries a "Standard/Source/Section" header on each chunk;
        # keep it once per chunk, it is cheap and keeps headings attached.
        body = "\n\n".join(c[2] for c in chunks).strip()
        if len(body) < 80:
            continue
        docs.append(SourceDoc(repo, artifact_id, path, body))
    docs.sort(key=lambda d: d.path)
    return docs


def load_repo_docs(session: Any, source_repo: str) -> List[SourceDoc]:
    from application.database.db import HarvestInput

    q = (
        session.query(
            HarvestInput.source_repo, HarvestInput.artifact_id, HarvestInput.payload
        )
        .filter(HarvestInput.source_repo == source_repo)
        .order_by(HarvestInput.created_at.desc())
    )
    seen: Dict[Tuple[str, str], bool] = {}
    rows = []
    for repo, artifact_id, payload in q:
        # Latest harvest wins: keep a chunk only from the newest run of its artifact.
        run = (payload or {}).get("pipeline_run_id") or ""
        key = (artifact_id, run)
        newest = next((k for k in seen if k[0] == artifact_id), None)
        if newest is not None and newest[1] != run:
            continue
        seen[key] = True
        rows.append((repo, artifact_id, payload))
    return docs_from_rows(rows)


def chunks_for_repo(session: Any, source_repo: str) -> List[Tuple[str, int, str]]:
    """(path, chunk_index, text) for the newest harvest of each artifact; noise and tiny chunks dropped."""
    from application.database.db import HarvestInput

    q = (
        session.query(HarvestInput.artifact_id, HarvestInput.payload)
        .filter(HarvestInput.source_repo == source_repo)
        .order_by(HarvestInput.created_at.desc())
    )
    newest: Dict[str, str] = {}
    seen = set()
    out: List[Tuple[str, int, str]] = []
    for artifact_id, payload in q:
        run = (payload or {}).get("pipeline_run_id") or ""
        if newest.setdefault(artifact_id, run) != run:
            continue
        loc = (payload or {}).get("locator") or {}
        path = str(
            (loc.get("path") if isinstance(loc, dict) else None)
            or str(artifact_id).split(":", 2)[-1]
        )
        text = str((payload or {}).get("text") or "").strip()
        idx = int(((payload or {}).get("span") or {}).get("index") or 0)
        if _RAW_NOISE.search(path or "") or len(text) < 60:
            continue
        if (path, idx) in seen:
            continue
        seen.add((path, idx))
        out.append((path, idx, text[:6000]))
    return out
