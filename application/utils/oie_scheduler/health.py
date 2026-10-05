"""Health of the scheduled OIE jobs and the queues between the modules.

Backs ``/admin/oie/health`` and ``scripts/monitor_oie_health.py``. A job is
``stale`` when its last successful run is older than ``STALE_AFTER_SLOTS`` slots:
a laptop that slept through one or two ticks is normal, one that missed a whole
day of the 10-minute job is not.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from application.database import db
from application.utils.oie_scheduler import run_log
from application.utils.oie_scheduler.jobs import JOBS

STALE_AFTER_SLOTS = 6


def queue_depths(session: Any) -> Dict[str, int]:
    return {
        "harvest_input_pending": session.query(db.HarvestInput)
        .filter(db.HarvestInput.status == "pending")
        .count(),
        "knowledge_queue_unconsumed": session.query(db.KnowledgeQueueItem)
        .filter(db.KnowledgeQueueItem.consumed_at.is_(None))
        .count(),
        "decision_queue_linked_unfiled": session.query(db.DecisionQueueItem)
        .filter(
            db.DecisionQueueItem.status == "linked",
            db.DecisionQueueItem.consumed_at.is_(None),
        )
        .count(),
        "decision_queue_review_required": session.query(db.DecisionQueueItem)
        .filter(db.DecisionQueueItem.status == "review_required")
        .count(),
    }


def _last(session: Any, job: str, *statuses: str) -> Optional[db.OieRun]:
    query = session.query(db.OieRun).filter(db.OieRun.job == job)
    if statuses:
        query = query.filter(db.OieRun.status.in_(statuses))
    return query.order_by(db.OieRun.started_at.desc()).first()


def job_health(session: Any, job: str, now: datetime) -> Dict[str, Any]:
    spec = JOBS[job]
    naive_now = run_log.naive_utc(now)
    last = _last(session, job)
    last_ok = _last(session, job, "ok", "degraded")
    stale_after = timedelta(minutes=spec.interval_minutes * STALE_AFTER_SLOTS)

    if last is None:
        state = "never_ran"
    elif last.status == "running":
        state = "running"
    elif (
        last_ok is None
        or naive_now - (last_ok.finished_at or last_ok.started_at) > stale_after
    ):
        state = "stale"
    elif last.status == "error":
        state = "failing"
    else:
        state = "ok"

    return {
        "job": job,
        "interval_minutes": spec.interval_minutes,
        "state": state,
        "last_run": run_log.run_to_dict(last) if last else None,
        "last_success_at": (
            (last_ok.finished_at or last_ok.started_at).isoformat() if last_ok else None
        ),
        "next_slot_at": run_log.expected_next(spec.interval_minutes, now).isoformat(),
    }


def evaluate_health(session: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    current = now or run_log.utcnow()
    jobs = {name: job_health(session, name, current) for name in JOBS}
    healthy = all(j["state"] in ("ok", "running") for j in jobs.values())
    return {
        "healthy": healthy,
        "checked_at": current.isoformat(),
        "jobs": jobs,
        "queues": queue_depths(session),
    }
