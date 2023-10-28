import os
import redis
from rq import Worker, Queue, Connection
from application.database import db
import logging
from application.cmd.cre_main import db_connect
from application.utils import redis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

listen = ["high", "default", "low"]


def start_worker(cache: str):
    conn = redis.connect()
    logger.info(f"Worker Starting")
    database = db_connect(path=cache)
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
