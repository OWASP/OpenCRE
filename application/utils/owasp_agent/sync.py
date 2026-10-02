"""Sync Nest + GitHub into the local OWASP agent index."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from application.utils.owasp_agent.github_crawler import (
    GitHubCrawler,
    GitHubCrawlerError,
)
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.nest_client import (
    NestAuthError,
    NestClient,
    NestClientError,
)


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
                    store.upsert_chapter(gh.parse_chapter_markdown(full_name, text))
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

    return report
