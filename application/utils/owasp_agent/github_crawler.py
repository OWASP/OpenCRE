"""GitHub crawler for OWASP public metadata (chapters, projects, board, staff)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from application.utils.owasp_agent.models import (
    BoardCandidate,
    BoardMember,
    Chapter,
    Project,
)

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"


class GitHubCrawlerError(Exception):
    """GitHub crawl failure."""


class GitHubCrawler:
    def __init__(
        self,
        token: Optional[str] = None,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
        sleep_s: float = 0.0,
    ) -> None:
        self.token = (token or "").strip()
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sleep_s = sleep_s

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "OpenCRE-owasp-agent/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = self.session.get(
            url, headers=self._headers(), params=params or {}, timeout=self.timeout
        )
        if resp.status_code >= 400:
            raise GitHubCrawlerError(f"GitHub HTTP {resp.status_code} for {url}")
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return resp.json()

    def _get_text(self, url: str) -> str:
        resp = self.session.get(
            url,
            headers={"User-Agent": "OpenCRE-owasp-agent/1.0"},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise GitHubCrawlerError(f"raw HTTP {resp.status_code} for {url}")
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return resp.text

    def list_org_repos(self, prefix: str, org: str = "OWASP") -> List[str]:
        """Return full_names matching name prefix via search API."""
        q = f"org:{org} in:name {prefix}"
        names: List[str] = []
        page = 1
        while True:
            data = self._get_json(
                f"{GITHUB_API}/search/repositories",
                params={"q": q, "per_page": 100, "page": page},
            )
            items = data.get("items") or []
            for item in items:
                name = item.get("full_name") or ""
                if name:
                    names.append(name)
            if len(items) < 100 or page >= 10:
                break
            page += 1
        return names

    def fetch_board_history(
        self, ref: str = "master"
    ) -> Tuple[List[BoardMember], List[BoardCandidate]]:
        url = f"{RAW_BASE}/OWASP/www-board/{ref}/_data/board-history.yml"
        text = self._get_text(url)
        return parse_board_history_yaml(text)

    def fetch_board_candidates_from_yaml(
        self, text: str, default_year: int
    ) -> List[BoardCandidate]:
        data = yaml.safe_load(text) or []
        out: List[BoardCandidate] = []
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                year = int(entry.get("year") or default_year)
                name = str(entry.get("name") or "").strip()
                if name:
                    out.append(
                        BoardCandidate(
                            year=year, name=name, notes=str(entry.get("notes") or "")
                        )
                    )
        return out

    def parse_chapter_markdown(self, repo_name: str, text: str) -> Chapter:
        meta, _ = split_frontmatter(text)
        key = repo_name.replace("OWASP/", "").replace("www-chapter-", "")
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return Chapter(
            key=key,
            name=str(meta.get("title") or key),
            country=str(meta.get("country") or ""),
            region=str(meta.get("region") or ""),
            city=str(meta.get("city") or ""),
            latitude=_opt_float(meta.get("latitude") or meta.get("lat")),
            longitude=_opt_float(meta.get("longitude") or meta.get("lon")),
            url=(
                f"https://owasp.org/{repo_name.split('/')[-1]}/"
                if "/" in repo_name
                else ""
            ),
            tags=list(tags) if isinstance(tags, list) else [],
            source="github",
            raw=meta,
        )

    def parse_project_markdown(self, repo_name: str, text: str) -> Project:
        meta, body = split_frontmatter(text)
        key = repo_name.replace("OWASP/", "").replace("www-project-", "")
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        desc = str(meta.get("pitch") or meta.get("description") or "")
        if not desc:
            desc = body.strip().split("\n\n")[0][:500] if body.strip() else ""
        return Project(
            key=key,
            name=str(meta.get("title") or key),
            level=str(meta.get("level") or ""),
            description=desc,
            url=(
                f"https://owasp.org/{repo_name.split('/')[-1]}/"
                if "/" in repo_name
                else ""
            ),
            tags=list(tags) if isinstance(tags, list) else [],
            source="github",
            raw=meta,
        )

    def fetch_repo_index_md(self, full_name: str, ref: str = "master") -> str:
        # try common default branches
        last_err: Optional[Exception] = None
        for branch in (ref, "main", "master"):
            url = f"{RAW_BASE}/{full_name}/{branch}/index.md"
            try:
                return self._get_text(url)
            except GitHubCrawlerError as exc:
                last_err = exc
                continue
        raise GitHubCrawlerError(
            str(last_err) if last_err else f"no index.md for {full_name}"
        )


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, text or ""
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, m.group(2) or ""


def parse_board_history_yaml(
    text: str,
) -> Tuple[List[BoardMember], List[BoardCandidate]]:
    data = yaml.safe_load(text) or []
    members: List[BoardMember] = []
    candidates: List[BoardCandidate] = []
    if not isinstance(data, list):
        return members, candidates
    for year_block in data:
        if not isinstance(year_block, dict):
            continue
        try:
            raw_year = year_block.get("year")
            if raw_year is None:
                continue
            year = int(raw_year)
        except (TypeError, ValueError):
            continue
        for m in year_block.get("members") or []:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or "").strip()
            if not name:
                continue
            members.append(
                BoardMember(
                    year=year,
                    name=name,
                    role=str(m.get("role") or "member"),
                    notes=str(m.get("notes") or ""),
                    source="github",
                    raw=m,
                )
            )
        for c in year_block.get("candidates") or []:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            candidates.append(
                BoardCandidate(
                    year=year,
                    name=name,
                    notes=str(c.get("notes") or ""),
                    source="github",
                    raw=c,
                )
            )
    return members, candidates


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
