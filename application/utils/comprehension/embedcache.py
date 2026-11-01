"""Embed each distinct text once per process (the router and retrieval both embed the question)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Sequence

_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_LOCK = threading.Lock()
_MAX = 256
_POOL = ThreadPoolExecutor(max_workers=4)
_PENDING: Dict[str, Any] = {}


def _store(text: str, vec: Any) -> Any:
    with _LOCK:
        _CACHE[text] = vec
        _CACHE.move_to_end(text)
        while len(_CACHE) > _MAX:
            _CACHE.popitem(last=False)
    return vec


def _quick(fn: Callable[[str], Any]) -> Callable[[str], Any]:
    """Embedding calls a person waits on retry transient provider errors quickly."""

    def _call(text: str) -> Any:
        from application.prompt_client import litellm_router

        return litellm_router.quick_retry(lambda: fn(text), context="query embedding")

    return _call


def cached(fn: Callable[[str], Any]) -> Callable[[str], Any]:
    """Wrap an embedding function with the shared cache (also joins in-flight prefetches)."""
    fn = _quick(fn)

    def _embed(text: str) -> Any:
        with _LOCK:
            hit = _CACHE.get(text)
            pending = _PENDING.get(text)
        if hit is not None:
            return hit
        if pending is not None:
            try:
                return pending.result(timeout=30)
            except Exception:
                pass
        return _store(text, fn(text))

    return _embed


def prefetch(text: str, fn: Callable[[str], Any]) -> None:
    """Start embedding ``text`` in the background so a later cached() call finds it."""
    with _LOCK:
        if text in _CACHE or text in _PENDING:
            return
        quick = _quick(fn)
        fut = _POOL.submit(lambda: _store(text, quick(text)))
        _PENDING[text] = fut

    def _done(_f: Any, t: str = text) -> None:
        with _LOCK:
            _PENDING.pop(t, None)

    fut.add_done_callback(_done)


def embed_many(texts: Sequence[str], fn: Callable[[str], Any]) -> List[Any]:
    """Embed several texts concurrently (cache-aware), preserving order."""
    wrapped = cached(fn)
    if len(texts) <= 1:
        return [wrapped(t) for t in texts]
    return list(_POOL.map(wrapped, texts))
