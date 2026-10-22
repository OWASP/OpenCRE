"""The scheduled OIE jobs and their stages.

Two jobs, both Postgres-only in production:

``owasp`` (every 10 minutes) -- the cheap, frequent one.
    1. ``agent_sync``: Nest + GitHub metadata into the OWASP agent index, plus
       the chapter repos that are due (the *metadata path*).
    2. ``harvest``: Module A over the harvestable repos whose polling interval
       has elapsed, capped per tick (the front of the *expansion path*).

``cre_expansion`` (daily) -- the expensive one, which spends LLM and embedding
calls on everything the harvester has accumulated.
    1. ``noise_filter``: Module B over every pending ``harvest_input`` run.
    2. ``librarian``: Module C over every unconsumed ``knowledge_queue`` run.
    3. ``file_graph``: file confident links into the graph (see ``graph_filer``).
    4. ``gap_analysis``: only when step 3 added standard edges.

A stage that fails is recorded and the job carries on with the remaining
stages: a Nest outage must not stop the harvester, and a Librarian outage must
not stop already-decided links from being filed.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import func

from application.database import db
from application.utils.db_url import redact_db_url
from application.utils.oie_scheduler import graph_filer


@dataclass(frozen=True)
class SchedulerConfig:
    harvest_max_repos: int = 25
    metadata_max_repos: int = 50
    file_floor: float = 0.9
    # Default off: Module C decisions stay for review until an operator enables filing.
    filing_enabled: bool = False
    repos_yaml: Optional[str] = None
    agent_db: Optional[str] = None

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        link_threshold = float(os.getenv("CRE_LIBRARIAN_LINK_THRESHOLD", "0.8"))
        floor = float(os.getenv("OIE_FILE_CONFIDENCE_FLOOR", "0.9"))
        # Filing below the Librarian's own link threshold would file links the
        # Librarian itself would not have called links.
        floor = max(floor, link_threshold)
        raw_filing = os.getenv("OIE_GRAPH_FILING_ENABLED", "0").strip().lower()
        return cls(
            harvest_max_repos=int(os.getenv("OIE_HARVEST_MAX_REPOS", "25")),
            metadata_max_repos=int(os.getenv("OIE_METADATA_MAX_REPOS", "50")),
            file_floor=floor,
            filing_enabled=raw_filing in ("1", "true", "yes", "on"),
            repos_yaml=os.getenv("OIE_REPOS_YAML") or None,
            agent_db=os.getenv("OWASP_AGENT_DB") or None,
        )


@dataclass
class StageResult:
    name: str
    status: str  # ok | degraded | error | skipped
    detail: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "duration_seconds": round(self.duration_seconds, 3),
            "summary": self.summary,
        }


StageFn = Callable[["JobContext"], StageResult]


@dataclass
class JobContext:
    collection: Any
    cache_file: str
    run_id: str
    now: datetime
    dry_run: bool = False
    config: SchedulerConfig = field(default_factory=SchedulerConfig)
    overrides: Dict[str, StageFn] = field(default_factory=dict)
    ga_fn: Optional[Callable[[str], None]] = None
    #: Results one stage hands to a later one (e.g. the filer's graph change).
    state: Dict[str, Any] = field(default_factory=dict)

    @property
    def session(self) -> Any:
        return self.collection.session


@dataclass(frozen=True)
class JobSpec:
    name: str
    interval_minutes: int
    description: str
    stages: tuple[tuple[str, StageFn], ...]


def _repos_file(ctx: JobContext) -> Any:
    from application.utils.harvester.config_loader import load_repo_config
    from application.utils.harvester.pipeline import DEFAULT_REPOS_YAML

    return load_repo_config(Path(ctx.config.repos_yaml or DEFAULT_REPOS_YAML))


def _agent_index_target(ctx: JobContext) -> str:
    if ctx.config.agent_db:
        return ctx.config.agent_db
    return ctx.session.get_bind().url.render_as_string(hide_password=False)


def stage_agent_sync(ctx: JobContext) -> StageResult:
    from application.utils.harvester.checkpoint_store import CheckpointStore
    from application.utils.harvester.models import RepositoryCheckpoint
    from application.utils.harvester.selection import select_repositories
    from application.utils.owasp_agent.index_store import IndexStore
    from application.utils.owasp_agent.sync import sync_all

    if ctx.dry_run:
        return StageResult("agent_sync", "skipped", "dry run: index not written")

    repos = _repos_file(ctx)
    checkpoints = CheckpointStore(session=ctx.session)
    chapters = select_repositories(
        repos.repositories,
        checkpoints,
        kinds={"chapter"},
        only_due=True,
        max_repos=ctx.config.metadata_max_repos,
        now=ctx.now,
    )
    full_names = [f"{r.owner}/{r.repo}" for r in chapters.selected]

    target = _agent_index_target(ctx)
    if not ctx.config.agent_db:
        logger.info("Writing agent index to the main app database")
    store = IndexStore(target)
    report = sync_all(
        store=store,
        github_chapter_repos=full_names,
        github_project_repos=[],
    )

    failed = {name for name in full_names if any(name in e for e in report.errors)}
    for repo in chapters.selected:
        if f"{repo.owner}/{repo.repo}" in failed:
            continue
        checkpoints.save(
            RepositoryCheckpoint(
                repository_id=repo.id,
                last_processed_commit="metadata-sync",
                updated_at=datetime.now(timezone.utc),
                provider="github",
                owner=repo.owner,
                repository=repo.repo,
                branch=repo.branch,
            )
        )

    summary = report.to_dict()
    summary["index_target"] = redact_db_url(target)
    summary["chapter_repos_synced"] = len(full_names) - len(failed)
    summary["chapter_repos_deferred"] = chapters.deferred
    summary["event_repos_configured"] = sum(
        1 for r in repos.repositories if r.kind == "event" and r.enabled
    )
    if not (report.nest_ok or report.github_ok):
        return StageResult("agent_sync", "error", "; ".join(report.errors), summary)
    if report.errors:
        return StageResult("agent_sync", "degraded", "; ".join(report.errors), summary)
    return StageResult("agent_sync", "ok", "", summary)


def stage_harvest(ctx: JobContext) -> StageResult:
    from application.utils.harvester.pipeline import run_harvester
    from application.utils.harvester.schemas import HARVESTABLE_KINDS

    summary = run_harvester(
        ctx.session,
        ctx.run_id,
        repos_yaml=ctx.config.repos_yaml,
        dry_run=ctx.dry_run,
        kinds=HARVESTABLE_KINDS,
        only_due=True,
        max_repos=ctx.config.harvest_max_repos,
        now=ctx.now,
    )
    data = asdict(summary)
    status = "ok" if summary.status == "ok" else "degraded"
    return StageResult("harvest", status, "", data)


def _pending_harvest_runs(session: Any) -> List[str]:
    rows = (
        session.query(db.HarvestInput.pipeline_run_id)
        .filter(db.HarvestInput.status == "pending")
        .group_by(db.HarvestInput.pipeline_run_id)
        .order_by(func.min(db.HarvestInput.created_at))
        .all()
    )
    return [r[0] for r in rows]


def _unconsumed_knowledge_runs(session: Any) -> List[str]:
    rows = (
        session.query(db.KnowledgeQueueItem.pipeline_run_id)
        .filter(db.KnowledgeQueueItem.consumed_at.is_(None))
        .group_by(db.KnowledgeQueueItem.pipeline_run_id)
        .order_by(func.min(db.KnowledgeQueueItem.created_at))
        .all()
    )
    return [r[0] for r in rows]


def _sum_into(total: Dict[str, Any], part: Dict[str, Any]) -> None:
    for key, value in part.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total[key] = total.get(key, 0) + value


def stage_noise_filter(ctx: JobContext) -> StageResult:
    from application.utils.noise_filter.pipeline import run_noise_filter

    run_ids = _pending_harvest_runs(ctx.session)
    if not run_ids:
        return StageResult("noise_filter", "skipped", "no pending harvest runs")
    totals: Dict[str, Any] = {"runs": len(run_ids)}
    degraded = 0
    for rid in run_ids:
        summary = run_noise_filter(ctx.session, rid, dry_run=ctx.dry_run)
        _sum_into(totals, asdict(summary))
        if summary.status == "degraded":
            degraded += 1
    totals["degraded_runs"] = degraded
    return StageResult("noise_filter", "degraded" if degraded else "ok", "", totals)


def stage_librarian(ctx: JobContext) -> StageResult:
    from application.utils.librarian.config_loader import load_config
    from application.utils.librarian.envelope_sink import (
        DbEnvelopeSink,
        NullEnvelopeSink,
    )
    from application.utils.librarian.factory import build_components
    from application.utils.librarian.queue_runner import run_librarian_queue

    run_ids = _unconsumed_knowledge_runs(ctx.session)
    if not run_ids:
        return StageResult("librarian", "skipped", "no unconsumed knowledge runs")

    cfg = load_config()
    components = build_components(ctx.collection, config=cfg)
    totals: Dict[str, Any] = {"runs": len(run_ids)}
    degraded = 0
    for rid in run_ids:
        sink = NullEnvelopeSink() if ctx.dry_run else DbEnvelopeSink(ctx.session, rid)
        summary = run_librarian_queue(
            ctx.session,
            rid,
            components,
            cfg,
            at=ctx.now,
            sink=sink,
            dry_run=ctx.dry_run,
        )
        _sum_into(totals, asdict(summary))
        if summary.status != "ok":
            degraded += 1
    totals["degraded_runs"] = degraded
    return StageResult("librarian", "degraded" if degraded else "ok", "", totals)


def stage_file_graph(ctx: JobContext) -> StageResult:
    repos = _repos_file(ctx)
    standard_repos = {
        f"{r.owner}/{r.repo}" for r in repos.repositories if r.kind == "standard"
    }
    result = graph_filer.file_linked_decisions(
        ctx.collection,
        floor=ctx.config.file_floor,
        enabled=ctx.config.filing_enabled,
        dry_run=ctx.dry_run,
        skip_repos=standard_repos,
        now=ctx.now,
    )
    ctx.state["filer"] = result
    if not result.enabled:
        return StageResult(
            "file_graph",
            "skipped",
            "kill switch off (OIE_GRAPH_FILING_ENABLED)",
            result.to_dict(),
        )
    return StageResult("file_graph", "ok", "", result.to_dict())


def _default_ga(cache_file: str) -> None:
    from application.cmd import cre_main

    cre_main.backfill_gap_analysis_only(cache_file, no_queue=True)


def stage_gap_analysis(ctx: JobContext) -> StageResult:
    filer = ctx.state.get("filer")
    if filer is None or not filer.graph_changed:
        return StageResult("gap_analysis", "skipped", "no standard edges were added")
    if ctx.dry_run:
        return StageResult("gap_analysis", "skipped", "dry run")
    (ctx.ga_fn or _default_ga)(ctx.cache_file)
    return StageResult(
        "gap_analysis",
        "ok",
        "",
        {"standards": list(filer.standards), "links_added": filer.links_added},
    )


def run_stage(name: str, fn: StageFn, ctx: JobContext) -> StageResult:
    """Run one stage, turning an exception into an ``error`` result."""
    started = time.monotonic()
    try:
        result = ctx.overrides.get(name, fn)(ctx)
    except Exception as exc:  # noqa: BLE001 -- recorded on the run, job continues
        ctx.session.rollback()
        logger.exception("stage %s failed", name)
        result = StageResult(name, "error", f"{type(exc).__name__}: {exc}")
    result.duration_seconds = time.monotonic() - started
    logger.info(
        "stage %s finished: %s",
        name,
        result.status,
        extra={"stage": name, "stage_status": result.status},
    )
    return result


JOBS: Dict[str, JobSpec] = {
    "owasp": JobSpec(
        name="owasp",
        interval_minutes=10,
        description="OWASP agent Nest+GitHub sync and incremental harvest",
        stages=(("agent_sync", stage_agent_sync), ("harvest", stage_harvest)),
    ),
    "cre_expansion": JobSpec(
        name="cre_expansion",
        interval_minutes=1440,
        description="Noise filter, Librarian, graph filing and gap analysis",
        stages=(
            ("noise_filter", stage_noise_filter),
            ("librarian", stage_librarian),
            ("file_graph", stage_file_graph),
            ("gap_analysis", stage_gap_analysis),
        ),
    ),
}

#: Order a full tick runs due jobs in: metadata/harvest first, expansion last.
JOB_ORDER = ("owasp", "cre_expansion")


def job_status(stages: List[StageResult]) -> str:
    """Roll stage results up to the job's status.

    ``ok`` when nothing went wrong, ``error`` when every stage that ran failed,
    otherwise ``degraded``.
    """
    ran = [s for s in stages if s.status != "skipped"]
    if not any(s.status in ("error", "degraded") for s in ran):
        return "ok"
    if ran and all(s.status == "error" for s in ran):
        return "error"
    return "degraded"
