"""Phase 7: Redis shared answer cache (flag replaces in-process-only)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, Protocol

from application.utils.rag_parity.flags import RagParityFlags, load_flags

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class InProcessAnswerCache:
    def __init__(self) -> None:
        self._store: Dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if item is None:
            return None
        expires, value = item
        if expires and expires < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires = time.time() + max(ttl_seconds, 1)
        self._store[key] = (expires, value)


class RedisAnswerCache:
    def __init__(self, conn: Any, *, prefix: str = "cre:answer:") -> None:
        self._conn = conn
        self._prefix = prefix

    def get(self, key: str) -> Optional[str]:
        raw = self._conn.get(self._prefix + key)
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._conn.setex(self._prefix + key, max(ttl_seconds, 1), value)


def cache_key(prompt: str, *, model: str = "") -> str:
    blob = f"{model}\n{prompt}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_answer_cache(
    flags: Optional[RagParityFlags] = None,
    *,
    redis_conn: Any = None,
) -> CacheBackend:
    cfg = flags or load_flags()
    if cfg.redis_answer_cache:
        if redis_conn is None:
            try:
                from application.utils import redis as redis_utils

                redis_conn = redis_utils.connect()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "CRE_RAG_PARITY_REDIS_ANSWER_CACHE=1 but Redis unavailable; "
                    "falling back to in-process cache"
                )
                return InProcessAnswerCache()
        return RedisAnswerCache(redis_conn)
    return InProcessAnswerCache()


def get_cached_answer(
    cache: CacheBackend, prompt: str, *, model: str = ""
) -> Optional[Dict[str, Any]]:
    raw = cache.get(cache_key(prompt, model=model))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def put_cached_answer(
    cache: CacheBackend,
    prompt: str,
    payload: Dict[str, Any],
    *,
    model: str = "",
    ttl_seconds: int = 3600,
) -> None:
    cache.set(
        cache_key(prompt, model=model),
        json.dumps(payload, ensure_ascii=False),
        ttl_seconds,
    )
