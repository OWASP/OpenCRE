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
SITE_DATA = f"{RAW_BASE}/OWASP/owasp.github.io/master/_data"
CANDIDATES_RAW = f"{RAW_BASE}/OWASP/www-board-candidates/master"


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

    def fetch_site_json(self, name: str) -> Any:
        """Fetch OWASP site ``_data/{name}.json`` (chapters, leaders, countries, …)."""
        url = f"{SITE_DATA}/{name}.json"
        resp = self.session.get(
            url,
            headers={"User-Agent": "OpenCRE-owasp-agent/1.0"},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise GitHubCrawlerError(f"site data HTTP {resp.status_code} for {url}")
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return resp.json()

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

    def fetch_election_candidate_pages(
        self, years: Optional[List[int]] = None
    ) -> List[BoardCandidate]:
        """Crawl www-board-candidates/{year}/*.md for statements."""
        years = years or list(range(2018, 2027))
        out: List[BoardCandidate] = []
        for year in years:
            listing_url = (
                f"{GITHUB_API}/repos/OWASP/www-board-candidates/contents/{year}"
            )
            try:
                listing = self._get_json(listing_url)
            except GitHubCrawlerError:
                continue
            if not isinstance(listing, list):
                continue
            for item in listing:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")
                if not name.endswith(".md") or name in ("info.md", "index.md"):
                    continue
                download = str(item.get("download_url") or "")
                if not download:
                    continue
                try:
                    text = self._get_text(download)
                except GitHubCrawlerError:
                    continue
                cand = parse_candidate_markdown(year, name, text)
                if cand:
                    out.append(cand)
        return out

    def parse_chapter_markdown(self, repo_name: str, text: str) -> Chapter:
        meta, body = split_frontmatter(text)
        key = repo_name.replace("OWASP/", "").replace("www-chapter-", "")
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        leaders = parse_leaders_from_markdown(body)
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
            leaders=leaders,
            level=str(meta.get("level") or ""),
            source="github",
            raw=meta,
        )

    def fetch_chapter_leaders_md(
        self, full_name: str, ref: str = "master"
    ) -> List[str]:
        for branch in (ref, "main", "master"):
            url = f"{RAW_BASE}/{full_name}/{branch}/leaders.md"
            try:
                text = self._get_text(url)
                return parse_leaders_from_markdown(text)
            except GitHubCrawlerError:
                continue
        return []

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
_LEADER_LINK_RE = re.compile(
    r"\[\s*([^\]\n]+?)\s*\]\s*\(\s*mailto:[^)]+\)", re.IGNORECASE
)
_LEADER_BULLET_RE = re.compile(r"^\s*[-*]\s+\[?([A-Z][^\]\n|(]+)")


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, text or ""
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, m.group(2) or ""


def parse_leaders_from_markdown(text: str) -> List[str]:
    leaders: List[str] = []
    for m in _LEADER_LINK_RE.finditer(text or ""):
        name = m.group(1).strip()
        if name and name.lower() != "open position" and name not in leaders:
            leaders.append(name)
    if leaders:
        return leaders
    for line in (text or "").splitlines():
        if "open position" in line.lower():
            continue
        m = _LEADER_BULLET_RE.match(line)
        if m:
            name = m.group(1).strip().rstrip("]")
            if name and name not in leaders:
                leaders.append(name)
    return leaders


def parse_candidate_markdown(
    year: int, filename: str, text: str
) -> Optional[BoardCandidate]:
    meta, body = split_frontmatter(text)
    name = str(meta.get("title") or "").strip()
    if not name:
        slug = filename.replace(".md", "").replace("_", " ").strip()
        name = " ".join(p.capitalize() for p in slug.split())
    if not name:
        return None
    excerpt = _statement_excerpt(body)
    slug = filename.replace(".md", "")
    url = f"https://owasp.org/www-board-candidates/{year}/{slug}"
    return BoardCandidate(
        year=year,
        name=name,
        notes=str(meta.get("notes") or ""),
        statement=excerpt,
        url=url,
        source="github",
        raw=meta,
    )


def _statement_excerpt(body: str, limit: int = 1200) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    m = re.search(
        r"(?:###?\s*About Me\b)(.*?)(?=\n###?\s|\n####\s|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    chunk = (m.group(1) if m else text).strip()
    if len(chunk) > limit:
        chunk = chunk[: limit - 1].rstrip() + "…"
    return chunk


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


def chapters_from_site_data(
    chapters: List[Dict[str, Any]],
    inactive: List[Dict[str, Any]],
    leaders: List[Dict[str, Any]],
) -> List[Chapter]:
    """Merge owasp.github.io chapters + inactive + leaders into Chapter rows."""
    inactive_keys = set()
    for item in inactive or []:
        if not isinstance(item, dict):
            continue
        if (
            item.get("region") == "Needs Website Update"
            or item.get("build") == "no pages"
        ):
            inactive_keys.add(_chapter_key_from_site(item))

    leaders_by_group: Dict[str, List[str]] = {}
    for row in leaders or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("group-type") or "").lower() != "chapter":
            continue
        group = str(row.get("group") or "").strip()
        name = str(row.get("name") or "").strip()
        if not group or not name or name.lower() == "open position":
            continue
        leaders_by_group.setdefault(group.lower(), []).append(name)

    out: List[Chapter] = []
    seen: set = set()
    for item in chapters or []:
        if not isinstance(item, dict):
            continue
        key = _chapter_key_from_site(item)
        if not key or key in seen:
            continue
        seen.add(key)
        title = str(item.get("title") or item.get("name") or key)
        chapter_leaders = list(leaders_by_group.get(title.lower(), []))
        if not chapter_leaders:
            chapter_leaders = list(
                leaders_by_group.get(f"owasp {item.get('name') or ''}".lower(), [])
            )
        active = key not in inactive_keys
        out.append(
            Chapter(
                key=key,
                name=title,
                country=str(item.get("country") or ""),
                region=str(item.get("region") or ""),
                city=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
                leaders=chapter_leaders,
                active=active,
                level=str(item.get("level") or ""),
                meetings=int(item.get("meetings") or 0),
                source="site",
                raw=item,
            )
        )
    for item in inactive or []:
        if not isinstance(item, dict):
            continue
        if (
            item.get("region") != "Needs Website Update"
            and item.get("build") != "no pages"
        ):
            continue
        key = _chapter_key_from_site(item)
        if not key:
            continue
        if key in seen:
            for ch in out:
                if ch.key == key:
                    ch.active = False
            continue
        seen.add(key)
        title = str(item.get("title") or item.get("name") or key)
        chapter_leaders = list(leaders_by_group.get(title.lower(), []))
        out.append(
            Chapter(
                key=key,
                name=title,
                country=str(item.get("country") or ""),
                region=str(item.get("region") or ""),
                city=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
                leaders=chapter_leaders,
                active=False,
                level=str(item.get("level") or ""),
                meetings=int(item.get("meetings") or 0),
                source="site",
                raw=item,
            )
        )
    return out


def _chapter_key_from_site(item: Dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    url = str(item.get("url") or "")
    if "www-chapter-" in name:
        return name.replace("www-chapter-", "").strip("/").lower()
    m = re.search(r"www-chapter-([^/]+)", url)
    if m:
        return m.group(1).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
