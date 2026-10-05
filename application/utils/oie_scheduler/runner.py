"""Run scheduled OIE jobs: lease, slot-derived run id, stages, durable record.

``cre.py --run_scheduled all`` (cron, every 10 minutes) calls ``run_due_jobs``;
each job decides for itself whether its current slot has already run, so the
daily job fires on the first tick of the day and every other tick is a no-op.
"""

from __future__ import annotations

from cre_logging import get_logger, log_context

logger = get_logger(__name__)

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from application.utils.oie_scheduler import run_log
from application.utils.oie_scheduler.jobs import (
    JOB_ORDER,
    JOBS,
    JobContext,
    SchedulerConfig,
    StageFn,
    StageResult,
    job_status,
    run_stage,
)
from application.utils.oie_scheduler.lease import job_lease


@dataclass
class RunOutcome:
    job: str
    run_id: str
    #: ok | degraded | error | skipped_already_ran | skipped_locked
    status: str
    stages: List[StageResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ran(self) -> bool:
        return not self.status.startswith("skipped")

    @property
    def failed(self) -> bool:
        return self.status == "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job": self.job,
            "run_id": self.run_id,
            "status": self.status,
            "error": self.error,
            "stages": [s.to_dict() for s in self.stages],
        }


def run_job(
    collection: Any,
    job_name: str,
    *,
    cache_file: str,
    now: Optional[datetime] = None,
    force: bool = False,
    dry_run: bool = False,
    trigger: str = "scheduled",
    config: Optional[SchedulerConfig] = None,
    overrides: Optional[Dict[str, StageFn]] = None,
    ga_fn: Optional[Callable[[str], None]] = None,
) -> RunOutcome:
    if job_name not in JOBS:
        raise ValueError(f"unknown job {job_name!r}; expected one of {sorted(JOBS)}")
    spec = JOBS[job_name]
    session = collection.session
    started = now or run_log.utcnow()
    slot = run_log.slot_for(spec.interval_minutes, started)
    run_id = run_log.run_id_for(job_name, slot)

    with log_context(run_id=run_id, job=job_name):
        with job_lease(session, job_name) as acquired:
            if not acquired:
                logger.info("job %s already running elsewhere; skipping", job_name)
                return RunOutcome(job_name, run_id, "skipped_locked")

            row = run_log.begin_run(
                session,
                job_name,
                slot,
                trigger=trigger,
                dry_run=dry_run,
                now=started,
                force=force,
            )
            if row is None:
                logger.info("slot %s already ran; skipping", slot)
                return RunOutcome(job_name, run_id, "skipped_already_ran")

            logger.info(
                "job %s started",
                job_name,
                extra={"trigger": trigger, "dry_run": dry_run, "attempt": row.attempts},
            )
            ctx = JobContext(
                collection=collection,
                cache_file=cache_file,
                run_id=run_id,
                now=started,
                dry_run=dry_run,
                config=config or SchedulerConfig.from_env(),
                overrides=dict(overrides or {}),
                ga_fn=ga_fn,
            )
            stages: List[StageResult] = []
            error: Optional[str] = None
            try:
                for name, fn in spec.stages:
                    with log_context(stage=name):
                        stages.append(run_stage(name, fn, ctx))
                status = job_status(stages)
            except Exception as exc:  # noqa: BLE001 -- the run row must close
                session.rollback()
                logger.exception("job %s crashed", job_name)
                status = "error"
                error = f"{type(exc).__name__}: {exc}"

            errors = [f"{s.name}: {s.detail}" for s in stages if s.status == "error"]
            if error is None and status == "error":
                error = "; ".join(errors) or None
            run_log.finish_run(
                session,
                row,
                status=status,
                summary={"stages": [s.to_dict() for s in stages]},
                error=error,
                now=run_log.utcnow(),
            )
            logger.info(
                "job %s finished: %s",
                job_name,
                status,
                extra={"job_status": status, "stages": [s.name for s in stages]},
            )
            return RunOutcome(job_name, run_id, status, stages, error)


def run_due_jobs(
    collection: Any,
    *,
    cache_file: str,
    jobs: Optional[List[str]] = None,
    **kwargs: Any,
) -> List[RunOutcome]:
    """Run each requested job (default all, in ``JOB_ORDER``) for its current slot."""
    names = jobs or list(JOB_ORDER)
    return [
        run_job(collection, name, cache_file=cache_file, **kwargs) for name in names
    ]
