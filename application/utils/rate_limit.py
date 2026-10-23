"""Per-account question limits for the chatbot and MCP ``ask`` (each question costs model credits).

Fixed windows (minute, hour, day) counted per signed-in email, shared by every web and MCP process through
Redis (falls back to in-process counters when Redis is unavailable). Admins get a multiple of the user limits.

Defaults (per account): 5 per minute, 40 per hour, 150 per day; admins x4.
Override with RATE_LIMIT_PER_MINUTE / _PER_HOUR / _PER_DAY, RATE_LIMIT_ADMIN_MULTIPLIER; exempt accounts with
RATE_LIMIT_EXEMPT_EMAILS=a@x.org,b@y.org; disable with RATE_LIMIT_ENABLED=0.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

WINDOWS: List[Tuple[str, int, str, int]] = [
    ("minute", 60, "RATE_LIMIT_PER_MINUTE", 5),
    ("hour", 3600, "RATE_LIMIT_PER_HOUR", 40),
    ("day", 86400, "RATE_LIMIT_PER_DAY", 150),
]


class RateLimited(Exception):
    def __init__(self, window: str, limit: int, retry_after: int) -> None:
        self.window, self.limit, self.retry_after = window, limit, retry_after
        super().__init__(self.message())

    def message(self) -> str:
        wait = max(1, self.retry_after)
        when = f"{wait} seconds" if wait < 120 else f"{(wait + 59) // 60} minutes"
        return f"You have reached the limit of {self.limit} questions per {self.window}. Please try again in about {when}."


def enabled() -> bool:
    return (os.environ.get("RATE_LIMIT_ENABLED", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _limit(env_name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(env_name, "") or default))
    except ValueError:
        return default


def limits_for(role: Optional[str]) -> List[Tuple[str, int, int]]:
    """[(window name, seconds, max questions)] for this role."""
    from application.utils import roles

    try:
        mult = max(1, int(os.environ.get("RATE_LIMIT_ADMIN_MULTIPLIER", "") or 4))
    except ValueError:
        mult = 4
    factor = mult if role == roles.ADMIN else 1
    return [
        (name, secs, _limit(env, default) * factor)
        for name, secs, env, default in WINDOWS
    ]


_mem: Dict[str, Tuple[int, float]] = {}
_mem_lock = threading.Lock()
_redis = {"conn": None, "tried": 0.0}


def _redis_conn():
    now = time.time()
    if _redis["conn"] is not None or now - _redis["tried"] < 30:
        return _redis["conn"]
    _redis["tried"] = now
    try:
        from application.utils import redis as redis_utils

        conn = redis_utils.connect()
        if conn is not None:
            conn.ping()
        _redis["conn"] = conn
    except Exception:  # noqa: BLE001 - fall back to in-process counters
        _redis["conn"] = None
    return _redis["conn"]


def _counts(keys: List[str]) -> List[int]:
    conn = _redis_conn()
    if conn is not None:
        try:
            return [int(v or 0) for v in conn.mget(keys)]
        except Exception:  # noqa: BLE001
            _redis["conn"] = None
    now = time.time()
    with _mem_lock:
        return [(_mem[k][0] if k in _mem and _mem[k][1] > now else 0) for k in keys]


def _incr(keys: List[Tuple[str, int]]) -> None:
    conn = _redis_conn()
    if conn is not None:
        try:
            pipe = conn.pipeline()
            for key, secs in keys:
                pipe.incr(key)
                pipe.expire(key, secs + 5)
            pipe.execute()
            return
        except Exception:  # noqa: BLE001
            _redis["conn"] = None
    now = time.time()
    with _mem_lock:
        for key, secs in keys:
            count, expires = _mem.get(key, (0, 0.0))
            _mem[key] = ((count if expires > now else 0) + 1, now + secs + 5)


def check_and_count(
    account: Optional[str], role: Optional[str], scope: str = "ask"
) -> None:
    """Raise :class:`RateLimited` when the account is over a limit; otherwise count this question."""
    if not enabled() or not (account or "").strip():
        return
    who = account.strip().lower()
    exempt = {
        e.strip().lower()
        for e in (os.environ.get("RATE_LIMIT_EXEMPT_EMAILS") or "").split(",")
        if e.strip()
    }
    if (
        who in exempt
    ):  # e.g. the evaluation account that asks hundreds of questions in a row
        return
    now = time.time()
    plan = [
        (f"rl:{scope}:{who}:{name}:{int(now // secs)}", name, secs, cap)
        for name, secs, cap in limits_for(role)
    ]
    counts = _counts([p[0] for p in plan])
    for (key, name, secs, cap), used in zip(plan, counts):
        if used >= cap:
            raise RateLimited(name, cap, int(secs - (now % secs)))
    _incr([(key, secs) for key, _, secs, _ in plan])


def reset_memory() -> None:
    """Test helper."""
    with _mem_lock:
        _mem.clear()
    _redis.update(conn=None, tried=time.time())
