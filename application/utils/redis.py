import redis
import os
import logging
from typing import Callable, List
import rq
import time

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def empty_queues(redis: redis.Redis):
    deleted_keys = 0
    for key in redis.scan_iter():
        deleted_keys += 1
        redis.delete(key)


def connect():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_no_ssl = os.getenv("REDIS_NO_SSL")
    if os.getenv("REDIS_HOST") and os.getenv("REDIS_PORT"):
        logger.debug(
            f'Attempting to connect to Redis instance using host and port at {os.getenv("REDIS_HOST")}:{os.getenv("REDIS_PORT")} using password? {"yes" if os.getenv("REDIS_PASSWORD", None) else "no"}. Using SSL? {False if redis_no_ssl else True}'
        )
        return redis.StrictRedis(
            host=os.getenv("REDIS_HOST"),
            port=os.getenv("REDIS_PORT"),
            password=os.getenv("REDIS_PASSWORD", None),
            ssl=False if redis_no_ssl else True,
            ssl_cert_reqs=None,
        )
    elif redis_url:
        redis_url = redis_url.strip()
        logger.debug(
            f"Attempting to connect to Redis instance using a URL at {redis_url}"
        )
        # Always use from_url so the DB index (e.g. /1), auth, and scheme match workers.
        # The previous branch built redis.Redis(host=..., port=...) without ``db=``, so any
        # REDIS_URL that was not exactly redis://localhost:6379 silently used DB 0 and
        # saw an empty RQ namespace.
        return redis.from_url(redis_url, decode_responses=False)
    else:
        logger.warning("Starting without Redis, functionality may be limited!")


def wait_for_jobs(jobs: List[rq.job.Job], callback: Callable = None):
    def do_nothing():
        pass

    def _job_label(job: rq.job.Job) -> str:
        # Prefer explicit standards pair when present on GA jobs.
        standards = (getattr(job, "kwargs", {}) or {}).get("standards")
        if isinstance(standards, list) and len(standards) >= 2:
            return f"{standards[0]}->{standards[1]}"
        desc = str(job.description or "")
        # Legacy separator in some places is " >> ".
        return desc.replace(" >> ", "->")

    def _is_import_job(label: str) -> bool:
        return label.startswith("import:")

    if not callback:
        callback = do_nothing
    poll_interval_s = int(os.environ.get("CRE_REDIS_WAIT_POLL_SECONDS", "10"))
    queued_hint_after_s = int(os.environ.get("CRE_REDIS_QUEUE_HINT_AFTER_SECONDS", "60"))
    seen_status: dict[str, str] = {}
    queued_since: dict[str, float] = {}
    while jobs:
        overdue_queued_labels: list[str] = []
        for job in list(jobs):
            label = _job_label(job)
            job_id = str(getattr(job, "id", label))
            status = str(job.get_status())
            if job.is_finished:
                if _is_import_job(label):
                    logger.info("%s imported", label.removeprefix("import:"))
                else:
                    logger.info("%s finished", label)
                seen_status.pop(job_id, None)
                queued_since.pop(job_id, None)
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_failed:
                logger.error("Job %s failed", label)
                seen_status.pop(job_id, None)
                queued_since.pop(job_id, None)
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_canceled:
                logger.error("Job %s was cancelled", label)
                seen_status.pop(job_id, None)
                queued_since.pop(job_id, None)
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_stopped:
                logger.error("Job %s was stopped", label)
                seen_status.pop(job_id, None)
                queued_since.pop(job_id, None)
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_queued:
                now = time.time()
                queued_since.setdefault(job_id, now)
                if seen_status.get(job_id) != status:
                    logger.info("job %s queued", label)
                    seen_status[job_id] = status
                elif now - queued_since[job_id] >= queued_hint_after_s:
                    overdue_queued_labels.append(label)
                    # reset timer so warning is periodic, not every poll
                    queued_since[job_id] = now
            elif not job.is_started:
                if seen_status.get(job_id) != status:
                    logger.info("job %s status=%s", label, status)
                    seen_status[job_id] = status
            else:
                if seen_status.get(job_id) != "started":
                    logger.info("waiting for %s", label)
                    seen_status[job_id] = "started"
        if overdue_queued_labels:
            sample_size = int(os.environ.get("CRE_REDIS_QUEUE_WARN_SAMPLE_SIZE", "5"))
            sample = ", ".join(overdue_queued_labels[:sample_size])
            remaining = max(0, len(overdue_queued_labels) - sample_size)
            tail = f", +{remaining} more" if remaining else ""
            logger.warning(
                "%s jobs still queued (>=%ss); ensure GA/import workers are running. Sample: %s%s",
                len(overdue_queued_labels),
                queued_hint_after_s,
                sample,
                tail,
            )

        time.sleep(poll_interval_s)
