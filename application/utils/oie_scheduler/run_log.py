"""Durable run records (``oie_run``): what ran, when, with what outcome."""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from application.database.db import OieRun

#: Terminal states that mean "this slot is done" and must not be re-run.
DONE_STATUSES = ("ok", "degraded")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def naive_utc(value: datetime) -> datetime:
    """Columns are timezone-naive UTC (the codebase convention for DateTime)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def slot_for(interval_minutes: int, now: datetime) -> str:
    """The schedule slot ``now`` falls in, e.g. ``20261005T1000Z`` for 10 minutes."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    width = interval_minutes * 60
    start = int(now.timestamp()) // width * width
    return datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y%m%dT%H%MZ")


def run_id_for(job: str, slot: str) -> str:
    return f"{job}-{slot}"


def begin_run(
    session: Any,
    job: str,
    slot: str,
    *,
    trigger: str,
    dry_run: bool,
    now: datetime,
    force: bool = False,
) -> Optional[OieRun]:
    """Open (or re-open) the run row for ``(job, slot)``; None if the slot is done.

    The id is derived from the slot, so a replayed tick finds its own row: a
    finished slot is skipped (unless ``force``), a failed or interrupted one is
    retried on the same row with ``attempts`` bumped. Any other ``running`` row
    for the job is a crashed predecessor -- the caller holds the lease, so it
    cannot still be running -- and is marked ``abandoned``.
    """
    run_id = run_id_for(job, slot)
    stamp = naive_utc(now)

    session.query(OieRun).filter(
        OieRun.job == job, OieRun.status == "running", OieRun.id != run_id
    ).update(
        {OieRun.status: "abandoned", OieRun.finished_at: stamp},
        synchronize_session=False,
    )

    row = session.get(OieRun, run_id)
    if row is None:
        row = OieRun(
            id=run_id,
            job=job,
            slot=slot,
            status="running",
            trigger=trigger,
            dry_run=dry_run,
            attempts=1,
            started_at=stamp,
        )
        session.add(row)
    else:
        if row.status in DONE_STATUSES and not force:
            session.commit()
            return None
        row.status = "running"
        row.trigger = trigger
        row.dry_run = dry_run
        row.attempts = (row.attempts or 1) + 1
        row.started_at = stamp
        row.finished_at = None
        row.summary = None
        row.error = None
    session.commit()
    return row


def finish_run(
    session: Any,
    run: OieRun,
    *,
    status: str,
    summary: Optional[Dict[str, Any]],
    error: Optional[str],
    now: datetime,
) -> None:
    run.status = status
    run.summary = summary
    run.error = error
    run.finished_at = naive_utc(now)
    session.commit()


def run_to_dict(row: OieRun) -> Dict[str, Any]:
    duration = None
    if row.started_at and row.finished_at:
        duration = round((row.finished_at - row.started_at).total_seconds(), 3)
    return {
        "id": row.id,
        "job": row.job,
        "slot": row.slot,
        "status": row.status,
        "trigger": row.trigger,
        "dry_run": bool(row.dry_run),
        "attempts": row.attempts,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_seconds": duration,
        "error": row.error,
        "summary": row.summary,
    }


def list_runs(
    session: Any,
    *,
    job: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[OieRun]:
    query = session.query(OieRun)
    if job:
        query = query.filter(OieRun.job == job)
    if status:
        query = query.filter(OieRun.status == status)
    return (
        query.order_by(OieRun.started_at.desc(), OieRun.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )


def get_run(session: Any, run_id: str) -> Optional[OieRun]:
    return session.get(OieRun, run_id)


def expected_next(interval_minutes: int, now: datetime) -> datetime:
    """Start of the slot after the one ``now`` is in (UTC)."""
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    width = interval_minutes * 60
    start = int(now.timestamp()) // width * width
    return datetime.fromtimestamp(start, tz=timezone.utc) + timedelta(seconds=width)
