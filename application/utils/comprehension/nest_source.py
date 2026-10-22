"""OWASP Nest as a comprehension source: current project profiles (leaders, level, dates) and issue titles.

Nest list endpoints answer HTTP 500 for page sizes above ~10, so every call uses ``page_size=10``.
Documents are attached to the project's repository slug, so reading a whole project (L4) and
normal retrieval both see them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

PAGE_SIZE = 10
_ISSUE_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)")


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def repo_name_key(repo: str) -> str:
    """OWASP/www-project-top-ten -> 'topten'; OWASP/CheatSheetSeries -> 'cheatsheetseries'."""
    name = repo.split("/")[-1]
    name = re.sub(r"^(www-project-|www-)", "", name, flags=re.I)
    return norm(name)


def map_projects_to_repos(project_keys: List[str], repos: List[str]) -> Dict[str, str]:
    """Nest project key -> repo ('OWASP/<name>') when the normalised names agree."""
    by_key: Dict[str, str] = {}
    for repo in repos:
        by_key.setdefault(repo_name_key(repo), repo)
    out: Dict[str, str] = {}
    for key in project_keys:
        repo = by_key.get(norm(key))
        if repo:
            out[key] = repo
    return out


def iter_items(get: Callable[[str], Any], path: str) -> Iterator[Dict[str, Any]]:
    """Pages through a Nest list endpoint with a safe page size; ``get(path_and_query)`` -> JSON."""
    page = 1
    while True:
        payload = get(f"{path}?page={page}&page_size={PAGE_SIZE}")
        for item in payload.get("items") or []:
            if isinstance(item, dict):
                yield item
        if not payload.get("has_next") or page > 5000:
            return
        page += 1


def profile_text(detail: Dict[str, Any], fetched: str) -> str:
    leaders = [str(x.get("name") or "").strip() for x in detail.get("leaders") or []]
    leaders = [n for n in leaders if n]
    lines = [
        f"OWASP Nest profile of the project '{detail.get('name') or detail.get('key')}' "
        f"(current data from nest.owasp.org, fetched {fetched}).",
        f"Project key: {detail.get('key')}.",
        f"Level: {detail.get('level') or 'unknown'}. Type: {detail.get('type') or 'unknown'}.",
        f"Created: {str(detail.get('created_at') or '')[:10]}. Last updated: {str(detail.get('updated_at') or '')[:10]}.",
        "Current project leaders: "
        + (", ".join(leaders) if leaders else "none listed")
        + ".",
    ]
    if detail.get("description"):
        lines.append(f"Description: {str(detail['description']).strip()}")
    return "\n".join(lines)


def issues_by_repo(
    items: Iterator[Dict[str, Any]], limit: int = 0
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    n = 0
    for it in items:
        m = _ISSUE_RE.search(str(it.get("url") or ""))
        if not m:
            continue
        out[f"{m.group(1)}/{m.group(2)}"].append({**it, "number": int(m.group(3))})
        n += 1
        if limit and n >= limit:
            break
    return out


def issue_chunks(issues: List[Dict[str, Any]], per_chunk: int = 40) -> List[str]:
    issues = sorted(issues, key=lambda i: -i["number"])
    chunks = []
    for start in range(0, len(issues), per_chunk):
        part = issues[start : start + per_chunk]
        lines = [
            f"#{i['number']} [{i.get('state') or '?'}] {str(i.get('title') or '').strip()} "
            f"(opened {str(i.get('created_at') or '')[:10]}, updated {str(i.get('updated_at') or '')[:10]})"
            for i in part
        ]
        chunks.append("GitHub issues (from OWASP Nest):\n" + "\n".join(lines))
    return chunks
