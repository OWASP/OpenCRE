"""Expand config sources into OpenCRE harvest configs vs agent repo list."""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from application.utils.harvester.dest_classifier import classify_github_repo
from application.utils.harvester.github_sources import (
    GithubSource,
    list_github_owner_repos,
    parse_github_source,
)
from application.utils.harvester.schemas import (
    ChunkingConfig,
    PathRules,
    PollingConfig,
    RepositoryConfig,
    ReposFile,
)

ListReposFn = Callable[[str], List[Dict[str, Any]]]


@dataclass
class HarvestPlan:
    opencre: List[RepositoryConfig] = field(default_factory=list)
    agent: List[Dict[str, str]] = field(default_factory=list)
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


def _repo_id(owner: str, repo: str, taken: Set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{owner}-{repo}".lower()).strip("-")
    if not base:
        base = "repo"
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _make_opencre_config(
    owner: str,
    repo: str,
    branch: str,
    taken_ids: Set[str],
) -> RepositoryConfig:
    return RepositoryConfig(
        id=_repo_id(owner, repo, taken_ids),
        type="github",
        enabled=True,
        owner=owner,
        repo=repo,
        branch=branch or "main",
        paths=PathRules(include=["**/*.md"], exclude=[]),
        chunking=ChunkingConfig(
            strategy="markdown_heading",
            max_tokens=1200,
            overlap_tokens=100,
        ),
        polling=PollingConfig(mode="incremental", interval_minutes=60),
    )


def resolve_sources(
    repos_file: ReposFile,
    *,
    list_owner_repos: Optional[ListReposFn] = None,
) -> HarvestPlan:
    """Turn sources + repository overrides into an ingest plan.

    Explicit ``repositories`` entries are always OpenCRE. Org/user sources are
    listed from GitHub here (indexer time), then classified.
    """
    list_fn = list_owner_repos or list_github_owner_repos
    plan = HarvestPlan()
    taken_ids = {cfg.id for cfg in repos_file.repositories}
    explicit: Dict[Tuple[str, str], RepositoryConfig] = {}
    for cfg in repos_file.repositories:
        key = (cfg.owner.casefold(), cfg.repo.casefold())
        explicit[key] = cfg
        if cfg.enabled:
            plan.opencre.append(cfg)

    seen: Set[Tuple[str, str]] = set(explicit.keys())
    parsed_sources: List[GithubSource] = []
    for raw in repos_file.sources:
        try:
            parsed_sources.append(parse_github_source(raw))
        except ValueError as exc:
            plan.errors.append(str(exc))
            plan.skipped += 1

    for source in parsed_sources:
        if source.is_org:
            try:
                remote = list_fn(source.owner)
            except ValueError as exc:
                logger.warning("failed to list GitHub owner %s: %s", source.owner, exc)
                plan.errors.append(str(exc))
                continue
            for item in remote:
                _add_discovered(
                    plan,
                    owner=source.owner,
                    item=item,
                    explicit=explicit,
                    seen=seen,
                    taken_ids=taken_ids,
                )
            continue
        assert source.repo is not None
        key = (source.owner.casefold(), source.repo.casefold())
        if key in seen:
            plan.skipped += 1
            continue
        dest = classify_github_repo(repo=source.repo, explicit_opencre=False)
        seen.add(key)
        if dest == "opencre":
            plan.opencre.append(
                _make_opencre_config(source.owner, source.repo, "main", taken_ids)
            )
        else:
            plan.agent.append(
                {"owner": source.owner, "repo": source.repo, "dest": "agent"}
            )
    return plan


def _add_discovered(
    plan: HarvestPlan,
    *,
    owner: str,
    item: Dict[str, Any],
    explicit: Dict[Tuple[str, str], RepositoryConfig],
    seen: Set[Tuple[str, str]],
    taken_ids: Set[str],
) -> None:
    repo_name = str(item.get("name") or "").strip()
    if not repo_name:
        plan.skipped += 1
        return
    if item.get("fork") or item.get("archived"):
        plan.skipped += 1
        return
    key = (owner.casefold(), repo_name.casefold())
    if key in seen:
        plan.skipped += 1
        return
    seen.add(key)
    dest = classify_github_repo(
        repo=repo_name,
        description=str(item.get("description") or "") or None,
        language=str(item.get("language") or "") or None,
        topics=item.get("topics") if isinstance(item.get("topics"), list) else None,
        explicit_opencre=key in explicit,
    )
    if dest == "opencre":
        plan.opencre.append(
            _make_opencre_config(
                owner,
                repo_name,
                str(item.get("default_branch") or "main"),
                taken_ids,
            )
        )
        return
    plan.agent.append({"owner": owner, "repo": repo_name, "dest": "agent"})
