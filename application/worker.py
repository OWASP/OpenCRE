from rq import Worker, Queue, Connection
import logging
from application.utils import redis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

listen = ["high", "default", "low"]

def start_worker():
    logger.info(f"Worker Starting")
    with Connection(redis.connect()):
        worker = Worker(map(Queue, listen))
        worker.work()
