import redis
import os
from urllib.parse import urlparse
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def connect():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_no_ssl = os.getenv("REDIS_NO_SSL")
    if os.getenv("REDIS_HOST") and os.getenv("REDIS_PORT"):
        logger.info(
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
        logger.info(
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
