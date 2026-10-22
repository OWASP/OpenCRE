"""Parse GitHub source URLs and list org/user repos for the indexer."""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import dataclass
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

GITHUB_API = "https://api.github.com"
GITHUB_PAGE_SIZE = 100
GITHUB_MAX_PAGES = 10
GITHUB_PROBE_TIMEOUT = 8
GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class GithubSource:
    raw: str
    owner: str
    repo: Optional[str]
    canonical: str

    @property
    def is_org(self) -> bool:
        return self.repo is None


def validate_github_owner(owner: str) -> str:
    owner = (owner or "").strip()
    if not GITHUB_OWNER_RE.fullmatch(owner):
        raise ValueError("owner must be a GitHub org or user login")
    return owner


def parse_github_source(raw: str) -> GithubSource:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty GitHub source")
    for prefix in ("https://", "http://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.lower().startswith("www."):
        text = text[4:]
    if "/" not in text.strip("/"):
        owner = validate_github_owner(text.strip("/"))
        return GithubSource(
            raw=raw.strip(),
            owner=owner,
            repo=None,
            canonical=f"github.com/{owner}/",
        )
    if not text.lower().startswith("github.com/"):
        raise ValueError("source must be github.com/org/ or github.com/org/repo")
    rest = text.split("/", 1)[1]
    parts = [part for part in rest.split("/") if part]
    if not parts:
        raise ValueError("source must be github.com/org/ or github.com/org/repo")
    owner = validate_github_owner(parts[0])
    if len(parts) == 1:
        return GithubSource(
            raw=raw.strip(),
            owner=owner,
            repo=None,
            canonical=f"github.com/{owner}/",
        )
    repo = parts[1]
    if not GITHUB_REPO_RE.fullmatch(repo):
        raise ValueError("invalid GitHub repository name")
    return GithubSource(
        raw=raw.strip(),
        owner=owner,
        repo=repo,
        canonical=f"github.com/{owner}/{repo}",
    )


def _github_http_status(url: str, *, timeout: float = GITHUB_PROBE_TIMEOUT) -> int:
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(64)
            return int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        try:
            exc.read()
        except Exception:
            pass
        return int(exc.code)
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc)).lower()
        if "timed out" in reason or "timeout" in reason:
            raise ValueError("GitHub request timed out") from exc
        raise ValueError("GitHub request failed") from exc
    except (OSError, TimeoutError) as exc:
        raise ValueError("GitHub request failed") from exc


def probe_github_source(source: GithubSource) -> None:
    """Reject an org/user or repo URL that GitHub cannot serve right now."""
    owner_q = urllib.parse.quote(source.owner, safe="")
    if source.repo:
        repo_q = urllib.parse.quote(source.repo, safe="")
        url = f"{GITHUB_API}/repos/{owner_q}/{repo_q}"
        _raise_if_inaccessible(url, source.canonical)
        return
    last_status = 0
    for kind in ("orgs", "users"):
        url = f"{GITHUB_API}/{kind}/{owner_q}"
        try:
            status = _github_http_status(url)
        except ValueError as exc:
            raise ValueError(f"{exc}: {source.canonical}") from exc
        if status == 200:
            return
        last_status = status
        if status != 404:
            raise ValueError(
                f"GitHub source is not accessible (HTTP {status}): {source.canonical}"
            )
    raise ValueError(
        f"GitHub source is not accessible (HTTP {last_status}): {source.canonical}"
        if last_status
        else f"GitHub source is not accessible: {source.canonical}"
    )


def _raise_if_inaccessible(url: str, canonical: str) -> None:
    try:
        status = _github_http_status(url)
    except ValueError as exc:
        raise ValueError(f"{exc}: {canonical}") from exc
    if status == 200:
        return
    raise ValueError(f"GitHub source is not accessible (HTTP {status}): {canonical}")


def probe_github_sources(raw_sources: List[Any]) -> None:
    seen: set[str] = set()
    for raw in raw_sources or []:
        if isinstance(raw, dict):
            text = str(raw.get("url") or "").strip()
        elif hasattr(raw, "url"):
            text = str(getattr(raw, "url") or "").strip()
        else:
            text = str(raw).strip() if raw is not None else ""
        if not text:
            continue
        source = parse_github_source(text)
        key = source.canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        probe_github_source(source)


def _github_headers() -> Dict[str, str]:
    headers = {
        "User-Agent": "OpenCRE-harvester",
        "Accept": "application/vnd.github+json",
    }
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def list_github_owner_repos(owner: str) -> List[Dict[str, Any]]:
    owner = validate_github_owner(owner)
    headers = _github_headers()
    last_404 = False
    for kind in ("orgs", "users"):
        collected: List[Dict[str, Any]] = []
        found = True
        for page in range(1, GITHUB_MAX_PAGES + 1):
            url = (
                f"{GITHUB_API}/{kind}/{urllib.parse.quote(owner, safe='')}/repos"
                f"?per_page={GITHUB_PAGE_SIZE}&page={page}"
            )
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    last_404 = True
                    found = False
                    break
                raise ValueError(f"GitHub API error {exc.code}") from exc
            except json.JSONDecodeError as exc:
                raise ValueError("GitHub API returned invalid JSON") from exc
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise ValueError("GitHub API request failed") from exc
            if not isinstance(payload, list):
                raise ValueError("GitHub API returned unexpected payload")
            collected.extend(item for item in payload if isinstance(item, dict))
            if len(payload) < GITHUB_PAGE_SIZE:
                break
        if found:
            return collected
    if last_404:
        raise ValueError(f"GitHub owner not found: {owner}")
    return []
