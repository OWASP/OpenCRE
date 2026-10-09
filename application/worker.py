from cre_logging import get_logger

logger = get_logger(__name__)

from rq import Worker, Queue
import os
from application.utils import redis


# Heroku / default workers must not consume ``oie`` (cache-only prod). Staging
# and dedicated OIE hosts set ``CRE_WORKER_QUEUES`` explicitly (e.g. ``oie,default``).
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
    # Durable admin toggles (filing) when DB is reachable — env still wins if set.
    try:
        from application.utils.admin_panel.runtime_settings import (
            hydrate_environ_from_db,
        )

        hydrate_environ_from_db()
    except Exception:  # noqa: BLE001
        logger.debug("runtime settings hydrate skipped", exc_info=True)
    worker = Worker(listen, connection=redis.connect())
    worker.work()
