"""Shared RQ queue snapshot for import_dashboard + Admin OIE queue tab."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from application.utils import redis

_IMPORT_QUEUES = ("high", "default", "low")


def ga_queue_name() -> str:
    return (os.environ.get("CRE_GA_QUEUE_NAME") or "ga").strip() or "ga"


def oie_queue_name() -> str:
    return (os.environ.get("CRE_OIE_QUEUE_NAME") or "oie").strip() or "oie"


def monitored_queue_names() -> Tuple[str, ...]:
    return _IMPORT_QUEUES + (ga_queue_name(), oie_queue_name())


def _fetch_job(conn: Any, queue: Queue, job_id: str) -> Any:
    try:
        return Job.fetch(job_id, connection=conn, serializer=queue.serializer)
    except NoSuchJobError:
        return None


def queue_summary(conn: Any | None = None) -> Dict[str, Dict[str, int]]:
    conn = conn or redis.connect()  # type: ignore[no-untyped-call]
    out: Dict[str, Dict[str, int]] = {}
    for qn in monitored_queue_names():
        q = Queue(name=qn, connection=conn)
        out[qn] = {
            "queued": len(q),
            "started": len(StartedJobRegistry(qn, connection=conn).get_job_ids()),
            "failed": len(FailedJobRegistry(qn, connection=conn).get_job_ids()),
            "deferred": len(DeferredJobRegistry(qn, connection=conn).get_job_ids()),
            "scheduled": len(
                ScheduledJobRegistry(qn, connection=conn).get_job_ids()  # type: ignore[no-untyped-call]
            ),
            "finished": len(FinishedJobRegistry(qn, connection=conn).get_job_ids()),
        }
    return out


def _job_rows(
    conn: Any,
    queue_name: str,
    *,
    registry: str,
    limit: int = 40,
    description_prefix: Optional[str] = None,
) -> List[Dict[str, Any]]:
    q = Queue(name=queue_name, connection=conn)
    if registry == "started":
        ids = StartedJobRegistry(queue_name, connection=conn).get_job_ids()
    elif registry == "failed":
        ids = FailedJobRegistry(queue_name, connection=conn).get_job_ids()
    elif registry == "finished":
        ids = list(FinishedJobRegistry(queue_name, connection=conn).get_job_ids())
        ids = list(reversed(ids[-limit:]))
    elif registry == "queued":
        ids = list(q.job_ids)[:limit]
    else:
        ids = []
    rows: List[Dict[str, Any]] = []
    for jid in ids[:limit]:
        job = _fetch_job(conn, q, jid)
        if job is None:
            continue
        desc = job.description or ""
        if description_prefix and not str(desc).startswith(description_prefix):
            continue
        rows.append(
            {
                "job_id": jid,
                "description": desc,
                "status": str(job.get_status()),
                "enqueued_at": (
                    job.enqueued_at.isoformat() if job.enqueued_at else None
                ),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            }
        )
    return rows


def oie_rq_status(*, limit: int = 40) -> Dict[str, Any]:
    """Payload for ``/admin/oie/rq/status`` and Admin UI."""
    conn = redis.connect()  # type: ignore[no-untyped-call]
    qn = oie_queue_name()
    queues = queue_summary(conn)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "oie_queue_name": qn,
        "queues": queues,
        "oie": {
            "queued": _job_rows(
                conn, qn, registry="queued", limit=limit, description_prefix="oie:"
            ),
            "started": _job_rows(
                conn, qn, registry="started", limit=limit, description_prefix="oie:"
            ),
            "failed": _job_rows(
                conn, qn, registry="failed", limit=limit, description_prefix="oie:"
            ),
            "finished": _job_rows(
                conn, qn, registry="finished", limit=limit, description_prefix="oie:"
            ),
        },
    }


def oie_run_queue_counts(session: Any, pipeline_run_id: str) -> Dict[str, int]:
    """DB-side progress counters for one OIE run."""
    from application.database.db import (
        DecisionQueueItem,
        HarvestInput,
        KnowledgeQueueItem,
    )

    rid = pipeline_run_id
    harvest_pending = (
        session.query(HarvestInput)
        .filter_by(pipeline_run_id=rid, status="pending")
        .count()
    )
    harvest_processed = (
        session.query(HarvestInput)
        .filter_by(pipeline_run_id=rid, status="processed")
        .count()
    )
    kq_open = (
        session.query(KnowledgeQueueItem)
        .filter(
            KnowledgeQueueItem.pipeline_run_id == rid,
            KnowledgeQueueItem.consumed_at.is_(None),
        )
        .count()
    )
    kq_consumed = (
        session.query(KnowledgeQueueItem)
        .filter(
            KnowledgeQueueItem.pipeline_run_id == rid,
            KnowledgeQueueItem.consumed_at.isnot(None),
        )
        .count()
    )
    dq = session.query(DecisionQueueItem).filter_by(pipeline_run_id=rid).count()
    return {
        "harvest_pending": harvest_pending,
        "harvest_processed": harvest_processed,
        "knowledge_unconsumed": kq_open,
        "knowledge_consumed": kq_consumed,
        "decision_rows": dq,
    }
