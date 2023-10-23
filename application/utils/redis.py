import redis
import os
from urllib.parse import urlparse


def connect():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    url = urlparse(redis_url)
    r = redis.Redis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        ssl=True,
        ssl_cert_reqs=None,
    )
    return r
