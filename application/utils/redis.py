import redis
import os
from urllib.parse import urlparse


def connect():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    if redis_url == "redis://localhost:6379":
        return redis.from_url(redis_url)
    else:
        url = urlparse(redis_url)
        return redis.Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            ssl=True,
            ssl_cert_reqs=None,
        )
