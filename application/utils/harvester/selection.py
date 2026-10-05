"""Which configured repositories a harvest run should visit.

A scheduled run must not re-clone every repository on every tick: with the whole
OWASP org configured, "all enabled repos" is over a thousand clones. Selection
narrows by ``kind`` and, for scheduled runs, by whether a repository's polling
interval has elapsed since its durable checkpoint was last written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Collection, Optional, Sequence

from application.utils.harvester.checkpoint_store import CheckpointStore
from application.utils.harvester.schemas import DEFAULT_HARVEST_KINDS, RepositoryConfig


@dataclass
class Selection:
    selected: list[RepositoryConfig] = field(default_factory=list)
    skipped_not_due: int = 0
    deferred: int = 0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def select_repositories(
    repositories: Sequence[RepositoryConfig],
    checkpoint_store: CheckpointStore,
    *,
    kinds: Optional[Collection[str]] = None,
    only_due: bool = False,
    max_repos: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Selection:
    """Pick the repositories to harvest, never-harvested first, then stalest.

    ``kinds`` defaults to the curated ``standard`` repos; chapter and event repos
    belong to the metadata path and are never cloned here. ``only_due`` drops a
    repository whose checkpoint is younger than its ``polling.interval_minutes``.
    ``max_repos`` caps the batch; the remainder is counted as ``deferred`` and
    is picked up on a later tick, since its checkpoint stays stale.
    """
    wanted = set(kinds) if kinds is not None else set(DEFAULT_HARVEST_KINDS)
    current = _as_utc(now) if now else datetime.now(timezone.utc)

    # (never harvested?, checkpoint time, original order)
    candidates: list[tuple[bool, datetime, int, RepositoryConfig]] = []
    skipped = 0
    for index, repo in enumerate(repositories):
        if not repo.enabled or repo.kind not in wanted:
            continue
        checkpoint = checkpoint_store.load(repo.id)
        if checkpoint is None:
            candidates.append(
                (False, datetime.min.replace(tzinfo=timezone.utc), index, repo)
            )
            continue
        last = _as_utc(checkpoint.updated_at)
        if only_due and current - last < timedelta(
            minutes=repo.polling.interval_minutes
        ):
            skipped += 1
            continue
        candidates.append((True, last, index, repo))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    ordered = [item[3] for item in candidates]
    deferred = 0
    if max_repos is not None and max_repos >= 0 and len(ordered) > max_repos:
        deferred = len(ordered) - max_repos
        ordered = ordered[:max_repos]
    return Selection(selected=ordered, skipped_not_due=skipped, deferred=deferred)
