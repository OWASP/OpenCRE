try:
    from rq import Worker, Queue
except (ValueError, ImportError):
    Worker, Queue = None, None

import logging
from application.utils import redis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

listen = ["high", "default", "low"]


def start_worker():
    if not Worker:
        logger.error(
            "RQ Worker is not supported on Windows (requires os.fork). "
            "Gap analysis will run synchronously in the web server instead."
        )
        return
    logger.info(f"Worker Starting")
    worker = Worker(listen, connection=redis.connect())
    worker.work()
