from rq import Worker, Queue
import logging
import os
from application.utils import redis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_LISTEN = ["high", "default", "low", "ga"]


def _listen_queues() -> list[str]:
    raw = os.environ.get("CRE_WORKER_QUEUES", "")
    if not raw:
        return DEFAULT_LISTEN
    parsed = [q.strip() for q in raw.split(",") if q.strip()]
    return parsed or DEFAULT_LISTEN


def start_worker():
    listen = _listen_queues()
    logger.info("Worker Starting (queues=%s)", ",".join(listen))
    worker = Worker(listen, connection=redis.connect())
    worker.work()
