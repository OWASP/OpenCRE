import redis
import os
from urllib.parse import urlparse
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
        logger.debug(
            f"Attempting to connect to Redis instance using a URL at {redis_url}"
        )
        if redis_url == "redis://localhost:6379":
            return redis.from_url(redis_url)
        else:
            url = urlparse(redis_url)
            return redis.Redis(
                host=url.hostname,
                port=url.port,
                password=url.password,
                ssl=False if redis_no_ssl else True,
                ssl_cert_reqs=None,
            )
    else:
        logger.warning("Starting without Redis, functionality may be limited!")


def wait_for_jobs(jobs: List[rq.job.Job], callback: Callable = None):
    def do_nothing():
        pass

    if not callback:
        callback = do_nothing
    while jobs:
        for job in jobs:
            if job.is_finished:
                logger.info(f"{job.description} finished")
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_failed:
                logger.fatal(f"Job {job.description} failed, check logs for reason")
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_canceled:
                logger.fatal(
                    f"Job {job.description} was cancelled, check logs for reason but this looks like a bug"
                )
                jobs.pop(jobs.index(job))
                callback()
            elif job.is_stopped:
                logger.fatal(
                    f"Job {job.description} was stopped, check logs for reason but this looks like a bug"
                )
                jobs.pop(jobs.index(job))
                callback()
            elif not job.is_started:
                logger.info(
                    f"job {job.description} is of unknown status {job.get_status()}"
                )
            else:
                logger.info(f"waiting for {job.description}")
        time.sleep(10)
