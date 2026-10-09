"""Enqueue OIE A/B/C jobs on the existing RQ worker fleet (queue ``oie``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cre_logging import get_logger
from rq import Queue
from rq.job import Job

from application.utils import redis
from application.utils.gap_analysis import GAP_ANALYSIS_TIMEOUT

logger = get_logger(__name__)

OIE_QUEUE_NAME = "oie"
_INFLIGHT_PREFIX = "oie:inflight"


def oie_queue_name() -> str:
    return (
        os.environ.get("CRE_OIE_QUEUE_NAME") or OIE_QUEUE_NAME
    ).strip() or OIE_QUEUE_NAME


def oie_job_timeout() -> str:
    return (os.environ.get("CRE_OIE_JOB_TIMEOUT") or GAP_ANALYSIS_TIMEOUT).strip()


def _timeout_seconds() -> int:
    raw = oie_job_timeout()
    if raw.endswith("s") and raw[:-1].isdigit():
        return int(raw[:-1])
    if raw.isdigit():
        return int(raw)
    return 129600


def _inflight_key(stage: str, pipeline_run_id: str, unit_id: str) -> str:
    return f"{_INFLIGHT_PREFIX}:{stage}:{pipeline_run_id}:{unit_id}"


def _claim_inflight(conn: Any, key: str) -> Optional[str]:
    """Return existing queued/started job id, or None if free to enqueue."""
    from rq.exceptions import NoSuchJobError
    from rq.job import JobStatus

    raw = conn.get(key)
    if not raw:
        return None
    job_id = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    try:
        existing = Job.fetch(job_id, connection=conn)
        if existing.get_status() in (JobStatus.QUEUED, JobStatus.STARTED):
            return job_id
    except NoSuchJobError:
        conn.delete(key)
    return None


def _record_inflight(conn: Any, key: str, job_id: str) -> None:
    conn.set(key, str(job_id))
    conn.expire(key, _timeout_seconds())


def _queue(conn: Any) -> Queue:
    return Queue(name=oie_queue_name(), connection=conn)


@dataclass
class EnqueueResult:
    run_id: str
    a_job_ids: List[str] = field(default_factory=list)
    skipped_inflight: List[str] = field(default_factory=list)
    repo_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "queue": oie_queue_name(),
            "a_job_ids": list(self.a_job_ids),
            "skipped_inflight": list(self.skipped_inflight),
            "repo_ids": list(self.repo_ids),
        }


def _load_repo_entries(
    repos_yaml: Optional[str],
    repo_ids: Optional[Sequence[str]] = None,
) -> List[Any]:
    from application.utils.harvester.config_loader import load_repo_config
    from application.utils.harvester.pipeline import DEFAULT_REPOS_YAML
    from application.utils.harvester.repos_validator import validate_repositories
    from application.utils.harvester.source_resolver import resolve_sources

    path = Path(repos_yaml) if repos_yaml else DEFAULT_REPOS_YAML
    repos_file = load_repo_config(path)
    validate_repositories(repos_file)
    harvest = list(repos_file.repositories)
    if repos_file.sources:
        harvest = list(resolve_sources(repos_file).opencre)
    if repo_ids is not None:
        wanted = set(repo_ids)
        harvest = [r for r in harvest if r.id in wanted]
    return harvest


def enqueue_oie_batch(
    *,
    pipeline_run_id: str,
    db_connection_str: str,
    repos_yaml: Optional[str] = None,
    repo_ids: Optional[Sequence[str]] = None,
    sync_repos: bool = True,
    dry_run: bool = False,
    skip_b: bool = False,
    skip_c: bool = False,
    wait: bool = False,
) -> EnqueueResult:
    """Enqueue one Module A RQ job per repository (fan-out entry point)."""
    if not pipeline_run_id or not str(pipeline_run_id).strip():
        raise ValueError("pipeline_run_id must be non-empty")

    repos = _load_repo_entries(repos_yaml, repo_ids=repo_ids)
    if not repos:
        raise ValueError("no repositories to enqueue for OIE RQ batch")

    conn = redis.connect()  # type: ignore[no-untyped-call]
    q = _queue(conn)
    result = EnqueueResult(run_id=pipeline_run_id.strip())
    jobs: List[Job] = []
    timeout = oie_job_timeout()

    for cfg in repos:
        unit = cfg.id
        key = _inflight_key("a", result.run_id, unit)
        existing = _claim_inflight(conn, key)
        if existing:
            result.skipped_inflight.append(f"a:{unit}={existing}")
            result.a_job_ids.append(existing)
            result.repo_ids.append(unit)
            continue
        source_repo = f"{cfg.owner}/{cfg.repo}"
        job = q.enqueue_call(
            description=f"oie:a:{unit}",
            func="application.utils.oie_rq.jobs.run_oie_a_job",
            kwargs={
                "pipeline_run_id": result.run_id,
                "repo_id": unit,
                "source_repo": source_repo,
                "db_connection_str": db_connection_str,
                "repos_yaml": repos_yaml,
                "sync_repos": sync_repos,
                "dry_run": dry_run,
                "skip_b": skip_b,
                "skip_c": skip_c,
            },
            timeout=timeout,  # type: ignore[arg-type]  # RQ accepts "Ns" strings
        )
        _record_inflight(conn, key, str(job.id))
        result.a_job_ids.append(str(job.id))
        result.repo_ids.append(unit)
        jobs.append(job)
        logger.info("enqueued OIE A job repo=%s job_id=%s", unit, job.id)

    if wait and jobs:
        redis.wait_for_jobs(jobs)
    return result


def enqueue_b_jobs_for_artifacts(
    *,
    pipeline_run_id: str,
    artifact_ids: Sequence[str],
    db_connection_str: str,
    dry_run: bool = False,
    skip_c: bool = False,
) -> List[str]:
    """Enqueue one B job per artifact_id (called from A worker)."""
    conn = redis.connect()  # type: ignore[no-untyped-call]
    q = _queue(conn)
    timeout = oie_job_timeout()
    job_ids: List[str] = []
    for artifact_id in artifact_ids:
        if not artifact_id or not str(artifact_id).strip():
            continue
        unit = str(artifact_id).strip()
        key = _inflight_key("b", pipeline_run_id, unit)
        existing = _claim_inflight(conn, key)
        if existing:
            job_ids.append(existing)
            continue
        job = q.enqueue_call(
            description=f"oie:b:{unit}",
            func="application.utils.oie_rq.jobs.run_oie_b_job",
            kwargs={
                "pipeline_run_id": pipeline_run_id,
                "artifact_id": unit,
                "db_connection_str": db_connection_str,
                "dry_run": dry_run,
                "skip_c": skip_c,
            },
            timeout=timeout,  # type: ignore[arg-type]
        )
        _record_inflight(conn, key, str(job.id))
        job_ids.append(str(job.id))
        logger.info("enqueued OIE B job artifact=%s job_id=%s", unit, job.id)
    return job_ids


def enqueue_c_job(
    *,
    pipeline_run_id: str,
    artifact_id: str,
    db_connection_str: str,
    dry_run: bool = False,
) -> Optional[str]:
    """Enqueue one C job for an artifact (called from B worker)."""
    if not artifact_id or not str(artifact_id).strip():
        return None
    unit = str(artifact_id).strip()
    conn = redis.connect()  # type: ignore[no-untyped-call]
    q = _queue(conn)
    key = _inflight_key("c", pipeline_run_id, unit)
    existing = _claim_inflight(conn, key)
    if existing:
        return existing
    job = q.enqueue_call(
        description=f"oie:c:{unit}",
        func="application.utils.oie_rq.jobs.run_oie_c_job",
        kwargs={
            "pipeline_run_id": pipeline_run_id,
            "artifact_id": unit,
            "db_connection_str": db_connection_str,
            "dry_run": dry_run,
        },
        timeout=oie_job_timeout(),  # type: ignore[arg-type]
    )
    _record_inflight(conn, key, str(job.id))
    logger.info("enqueued OIE C job artifact=%s job_id=%s", unit, job.id)
    return str(job.id)


def oie_queue_inflight_counts(conn: Any | None = None) -> Dict[str, int]:
    """Queued + started (+ deferred/scheduled) depth on the OIE queue."""
    from rq.registry import (
        DeferredJobRegistry,
        ScheduledJobRegistry,
        StartedJobRegistry,
    )

    conn = conn or redis.connect()  # type: ignore[no-untyped-call]
    qn = oie_queue_name()
    q = Queue(name=qn, connection=conn)
    return {
        "queued": len(q),
        "started": len(StartedJobRegistry(qn, connection=conn).get_job_ids()),
        "deferred": len(DeferredJobRegistry(qn, connection=conn).get_job_ids()),
        "scheduled": len(
            ScheduledJobRegistry(qn, connection=conn).get_job_ids()  # type: ignore[no-untyped-call]
        ),
    }


def wait_for_oie_queue_idle(
    *,
    poll_seconds: float = 10.0,
    max_wait_seconds: Optional[float] = None,
    stable_polls: int = 3,
) -> Dict[str, int]:
    """Block until the OIE queue stays empty for ``stable_polls`` consecutive polls.

    Nested B/C jobs are enqueued by A/B workers after A finishes, so a single
    empty snapshot can race a fan-out gap — require a stable idle streak.
    """
    import time

    if stable_polls < 1:
        raise ValueError("stable_polls must be >= 1")

    conn = redis.connect()  # type: ignore[no-untyped-call]
    started = time.monotonic()
    idle_streak = 0
    while True:
        counts = oie_queue_inflight_counts(conn)
        active = (
            counts["queued"]
            + counts["started"]
            + counts["deferred"]
            + counts["scheduled"]
        )
        if active == 0:
            idle_streak += 1
            if idle_streak >= stable_polls:
                return counts
            logger.info(
                "OIE queue empty streak %s/%s: %s",
                idle_streak,
                stable_polls,
                counts,
            )
        else:
            idle_streak = 0
            logger.info("waiting for OIE queue idle: %s", counts)
        if (
            max_wait_seconds is not None
            and (time.monotonic() - started) > max_wait_seconds
        ):
            raise TimeoutError(
                f"OIE queue still busy after {max_wait_seconds}s: {counts}"
            )
        time.sleep(poll_seconds)
