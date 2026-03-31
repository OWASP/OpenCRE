from rq import Worker, Queue
import logging
from application.utils import redis
from application.utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

listen = ["high", "default", "low"]


def start_worker():
    logger.info(f"Worker Starting")
    worker = Worker(listen, connection=redis.connect())
    worker.work()
