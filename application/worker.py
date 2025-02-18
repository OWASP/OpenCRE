from rq import Worker, Queue
import logging
from application.utils import redis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

listen = ["high", "default", "low"]


def start_worker():
    logger.info(f"Worker Starting")
    worker = Worker(listen, connection=redis.connect())
    worker.work()
