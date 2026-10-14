"""Sync Nest + GitHub into the local OWASP agent index."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from application.utils.owasp_agent.github_crawler import (
    GitHubCrawler,
    GitHubCrawlerError,
    chapters_from_site_data,
    match_project_leader_group,
    project_leaders_from_site_data,
)
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.models import Project
from application.utils.owasp_agent.nest_client import (
    NestAuthError,
    NestClient,
    NestClientError,
)


# Curated blurbs when Nest has no project row but leaders.json lists the group.
_GROUP_PROJECT_BLURBS = {
    "owasp ai exchange": (
        "OWASP AI Exchange (AI security and privacy guide): community guidance on "
        "privacy-preserving and secure AI systems; material at owaspai.org."
    ),
    "ai exchange": (
        "OWASP AI Exchange (AI security and privacy guide): community guidance on "
        "privacy-preserving and secure AI systems; material at owaspai.org."
    ),
    "owasp genai security project": (
        "OWASP GenAI Security Project: global initiative for generative AI and "
        "Large Language Model security risks (successor home for LLM Top 10 work)."
    ),
    "genai security project": (
        "OWASP GenAI Security Project: global initiative for generative AI and "
        "Large Language Model security risks (successor home for LLM Top 10 work)."
    ),
}


def _project_key_from_group(group: str, group_url: str) -> str:
    tail = (group_url or "").rstrip("/").split("/")[-1].strip()
    if tail.startswith("www-project-"):
        return tail[len("www-project-") :]
    if tail:
        return re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
    slug = re.sub(r"^owasp\s+", "", (group or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "unknown-project"


def apply_project_leaders_from_site(store: IndexStore, leaders: List[Any]) -> int:
    """Index project leaders from site ``leaders.json`` and attach to projects.

    When Nest/GitHub never indexed the group as a project, create a site stub so
    person/compare queries still resolve (additive; does not delete Nest rows).
    """
    rows = project_leaders_from_site_data(leaders if isinstance(leaders, list) else [])
    if not rows:
        return 0
    projects = store.list_entities("project")
    # Merge by project key across sources for leader updates.
    by_key: dict = {}
    for p in projects:
        key = str(p.get("key") or "")
        if not key:
            continue
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = dict(p)
        else:
            # Prefer non-empty fields; union leaders later.
            for field in ("name", "url", "description", "level"):
                if p.get(field) and not cur.get(field):
                    cur[field] = p.get(field)
            tags = list(cur.get("tags") or [])
            for t in p.get("tags") or []:
                if t not in tags:
                    tags.append(t)
            cur["tags"] = tags

    applied = 0
    for row in rows:
        name = row["name"]
        group = row["group"]
        group_url = row.get("group_url") or ""
        email = row.get("email") or ""
        store.upsert_entity(
            "project_leader",
            f"{name.lower()}::{group.lower()}",
            name,
            "site",
            {
                "name": name,
                "group": group,
                "group_url": group_url,
                "email": email,
                "source": "site",
            },
        )
        applied += 1
        matched = False
        for key, proj in by_key.items():
            if not match_project_leader_group(
                str(proj.get("name") or ""),
                str(proj.get("url") or ""),
                group,
                group_url,
            ):
                continue
            matched = True
            leaders_list = list(proj.get("leaders") or [])
            if name not in leaders_list:
                leaders_list.append(name)
            proj["leaders"] = leaders_list
            store.upsert_project(
                Project(
                    key=key,
                    name=str(proj.get("name") or key),
                    level=str(proj.get("level") or ""),
                    description=str(proj.get("description") or ""),
                    url=str(proj.get("url") or ""),
                    tags=list(proj.get("tags") or []),
                    leaders=leaders_list,
                    source=str(
                        proj.get("source") or proj.get("_index_source") or "site"
                    ),
                    raw=dict(proj.get("raw") or {}),
                )
            )
        if matched:
            continue
        # Additive stub so compare/person_lookup can resolve site-only groups.
        stub_key = _project_key_from_group(group, group_url)
        g_norm = re.sub(r"^owasp\s+", "", group.lower()).strip()
        blurb = _GROUP_PROJECT_BLURBS.get(group.lower()) or _GROUP_PROJECT_BLURBS.get(
            g_norm
        )
        existing = by_key.get(stub_key) or {}
        leaders_list = list(existing.get("leaders") or [])
        if name not in leaders_list:
            leaders_list.append(name)
        desc = str(existing.get("description") or blurb or "")
        tags = list(existing.get("tags") or [])
        for t in ("ai", "ai security"):
            if "ai" in g_norm and t not in tags:
                tags.append(t)
        if "genai" in g_norm or "llm" in g_norm:
            for t in ("genai", "llm"):
                if t not in tags:
                    tags.append(t)
        stub = Project(
            key=stub_key,
            name=str(existing.get("name") or group),
            level=str(existing.get("level") or ""),
            description=desc,
            url=str(existing.get("url") or group_url or ""),
            tags=tags,
            leaders=leaders_list,
            source="site",
            raw={"from_leaders_json": True, "group": group},
        )
        store.upsert_project(stub)
        by_key[stub_key] = stub.to_dict()
    return applied


def ensure_known_meta_projects(store: IndexStore) -> int:
    """Upsert a few high-signal projects Nest often omits (additive stubs)."""
    known = [
        Project(
            key="ai-security-and-privacy-guide",
            name="OWASP AI Exchange",
            level="",
            description=_GROUP_PROJECT_BLURBS["owasp ai exchange"],
            url="https://owasp.org/www-project-ai-security-and-privacy-guide/",
            tags=["ai", "ai security", "privacy"],
            source="site",
            raw={"curated_meta": True},
        ),
        Project(
            key="genai-security-project",
            name="OWASP GenAI Security Project",
            level="",
            description=_GROUP_PROJECT_BLURBS["owasp genai security project"],
            url="https://genai.owasp.org/",
            tags=["genai", "llm", "ai"],
            source="site",
            raw={"curated_meta": True},
        ),
        Project(
            key="top-10-for-large-language-model-applications",
            name="OWASP Top 10 for Large Language Model Applications",
            level="",
            description=(
                "Legacy entry for Large Language Model Top 10; active GenAI Security "
                "Project work covers generative AI and LLM risks at genai.owasp.org."
            ),
            url="https://owasp.org/www-project-top-10-for-large-language-model-applications/",
            tags=["genai", "llm", "large language"],
            source="site",
            raw={"curated_meta": True},
        ),
    ]
    n = 0
    existing = {str(p.get("key") or ""): p for p in store.list_entities("project")}
    for proj in known:
        cur = existing.get(proj.key) or {}
        # Do not clobber richer Nest/GitHub descriptions.
        if cur.get("description") and not (cur.get("raw") or {}).get("curated_meta"):
            if not cur.get("name"):
                continue
            # Still refresh empty name/url only.
            continue
        leaders = list(cur.get("leaders") or proj.leaders or [])
        desc = str(cur.get("description") or proj.description)
        store.upsert_project(
            Project(
                key=proj.key,
                name=str(cur.get("name") or proj.name),
                level=str(cur.get("level") or proj.level),
                description=desc,
                url=str(cur.get("url") or proj.url),
                tags=list(cur.get("tags") or proj.tags or []),
                leaders=leaders,
                source=str(cur.get("source") or proj.source),
                raw=dict(cur.get("raw") or proj.raw or {}),
            )
        )
        n += 1
    return n


@dataclass
class SyncReport:
    nest_ok: bool = False
    github_ok: bool = False
    chapters: int = 0
    projects: int = 0
    events: int = 0
    board_members: int = 0
    board_candidates: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nest_ok": self.nest_ok,
            "github_ok": self.github_ok,
            "chapters": self.chapters,
            "projects": self.projects,
            "events": self.events,
            "board_members": self.board_members,
            "board_candidates": self.board_candidates,
            "errors": list(self.errors),
        }


def sync_all(
    store: Optional[IndexStore] = None,
    nest: Optional[NestClient] = None,
    github: Optional[GitHubCrawler] = None,
    skip_nest: bool = False,
    skip_github: bool = False,
    github_chapter_repos: Optional[List[str]] = None,
    github_project_repos: Optional[List[str]] = None,
) -> SyncReport:
    store = store or IndexStore()
    report = SyncReport()

    if not skip_nest:
        try:
            client = nest or NestClient()
            chapters = client.list_chapters()
            for ch in chapters:
                store.upsert_chapter(ch)
            projects = client.list_projects()
            for p in projects:
                store.upsert_project(p)
            events = client.list_events()
            for ev in events:
                store.upsert_event(ev)
            report.nest_ok = True
            report.chapters += len(chapters)
            report.projects += len(projects)
            report.events += len(events)
            store.log_sync(
                "nest",
                "ok",
                f"chapters={len(chapters)} projects={len(projects)} events={len(events)}",
            )
        except NestAuthError as exc:
            report.errors.append(f"nest_auth: {exc}")
            store.log_sync("nest", "auth_error", str(exc))
        except NestClientError as exc:
            report.errors.append(f"nest: {exc}")
            store.log_sync("nest", "error", str(exc))

    if not skip_github:
        try:
            gh = github or GitHubCrawler(token=os.environ.get("GITHUB_TOKEN", ""))
            members, candidates = gh.fetch_board_history()
            for m in members:
                store.upsert_board_member(m)
            for c in candidates:
                store.upsert_board_candidate(c)
            report.board_members = len(members)
            report.board_candidates = len(candidates)

            # Site metadata: chapters + inactive + leaders + membership countries
            try:
                site_chapters = gh.fetch_site_json("chapters")
                site_inactive = gh.fetch_site_json("inactive_chapters")
                site_leaders = gh.fetch_site_json("leaders")
                site_countries = gh.fetch_site_json("countries")
                merged = chapters_from_site_data(
                    site_chapters if isinstance(site_chapters, list) else [],
                    site_inactive if isinstance(site_inactive, list) else [],
                    site_leaders if isinstance(site_leaders, list) else [],
                )
                for ch in merged:
                    store.upsert_chapter(ch)
                report.chapters += len(merged)
                leader_n = apply_project_leaders_from_site(
                    store,
                    site_leaders if isinstance(site_leaders, list) else [],
                )
                if isinstance(site_countries, list):
                    for row in site_countries:
                        if not isinstance(row, dict):
                            continue
                        cname = str(row.get("name") or "").strip()
                        if not cname:
                            continue
                        store.upsert_entity(
                            "membership_country",
                            cname.lower(),
                            cname,
                            "site",
                            {
                                "name": cname,
                                "discount": bool(row.get("discount")),
                                "source": "site",
                            },
                        )
                store.log_sync(
                    "site_data",
                    "ok",
                    (
                        f"chapters={len(merged)} "
                        f"project_leaders={leader_n} "
                        f"countries={len(site_countries) if isinstance(site_countries, list) else 0}"
                    ),
                )
            except (GitHubCrawlerError, AttributeError, TypeError, ValueError) as exc:
                report.errors.append(f"site_data: {exc}")
                store.log_sync("site_data", "error", str(exc))

            # Board candidate statements (www-board-candidates)
            try:
                election_cands = gh.fetch_election_candidate_pages()
                for c in election_cands:
                    store.upsert_board_candidate(c)
                report.board_candidates += len(election_cands)
            except (GitHubCrawlerError, AttributeError, TypeError, ValueError) as exc:
                report.errors.append(f"board_candidates: {exc}")

            chapter_repos = github_chapter_repos
            project_repos = github_project_repos
            if (
                chapter_repos is None
                and os.environ.get("OWASP_AGENT_CRAWL_REPOS", "") == "1"
            ):
                chapter_repos = [
                    n for n in gh.list_org_repos("www-chapter") if "www-chapter-" in n
                ]
            if (
                project_repos is None
                and os.environ.get("OWASP_AGENT_CRAWL_REPOS", "") == "1"
            ):
                project_repos = [
                    n for n in gh.list_org_repos("www-project") if "www-project-" in n
                ]

            for full_name in chapter_repos or []:
                try:
                    text = gh.fetch_repo_index_md(full_name)
                    ch = gh.parse_chapter_markdown(full_name, text)
                    if not ch.leaders:
                        ch.leaders = gh.fetch_chapter_leaders_md(full_name)
                    store.upsert_chapter(ch)
                    report.chapters += 1
                except GitHubCrawlerError as exc:
                    report.errors.append(f"chapter {full_name}: {exc}")

            for full_name in project_repos or []:
                try:
                    text = gh.fetch_repo_index_md(full_name)
                    store.upsert_project(gh.parse_project_markdown(full_name, text))
                    report.projects += 1
                except GitHubCrawlerError as exc:
                    report.errors.append(f"project {full_name}: {exc}")

            report.github_ok = True
            store.log_sync(
                "github",
                "ok",
                f"board_members={report.board_members} candidates={report.board_candidates}",
            )
        except GitHubCrawlerError as exc:
            report.errors.append(f"github: {exc}")
            store.log_sync("github", "error", str(exc))
        except (
            Exception
        ) as exc:  # noqa: BLE001 — surface unexpected crawl errors in report
            report.errors.append(f"github: {exc}")
            store.log_sync("github", "error", str(exc))

    curated_n = ensure_known_meta_projects(store)
    if curated_n:
        store.log_sync("curated_meta", "ok", f"projects={curated_n}")

    return report
