"""Batch Module C query embeddings.

Prior-caged retrieval calls the inner retriever several times with the same
chunk text (global, allowlist, edition retry, preferred materialize). Dual-index
retrieval then embeds the header and the body on every one of those calls.
A process-local cache collapses those repeats, and ``prefetch`` sends the
unique strings for a queue batch to the embedder in list calls.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

EmbedFn = Callable[..., object]

# Child attributes that wrap another retriever. Walked so a cache installed on
# the pipeline retriever reaches every ``CandidateRetriever._embed_fn``.
_CHILD_ATTRS = ("_inner", "_names", "_summaries", "_standard")

_OFF = {"0", "false", "off", "no"}


def embed_batch_enabled() -> bool:
    return os.environ.get("CRE_LIBRARIAN_EMBED_BATCH", "1").strip().lower() not in _OFF


def embed_batch_size() -> int:
    raw = os.environ.get("CRE_LIBRARIAN_EMBED_BATCH_SIZE", "32")
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return 32
    return max(1, size)


def texts_for_retrieval(text: str) -> List[str]:
    """Strings ``retrieve`` may embed for one chunk.

    Includes the full chunk (standard-hop and the dual-index fallback) plus the
    name-pack header and narrative body.
    """
    from application.utils.librarian.focus_query import split_retrieval_query

    header, body = split_retrieval_query(text or "")
    out: List[str] = []
    if text:
        out.append(text)
    if header:
        out.append(header)
    if body and body != text:
        out.append(body)
    return out


class QueryEmbedCache:
    """``embed_fn`` replacement: list prefetch, then per-string cache hits."""

    def __init__(self, embed_fn: EmbedFn, *, batch_size: Optional[int] = None) -> None:
        self._embed_fn = embed_fn
        self._batch_size = (
            embed_batch_size() if batch_size is None else max(1, batch_size)
        )
        self._cache: Dict[str, List[float]] = {}

    def __call__(self, text: str) -> List[float]:
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = _as_vector(self._embed_fn(text))
        self._cache[text] = vector
        return vector

    def prefetch(self, texts: Sequence[str]) -> int:
        """Embed unique missing texts. Returns how many were newly embedded."""
        missing: List[str] = []
        seen = set()
        for text in texts:
            if not text or text in self._cache or text in seen:
                continue
            seen.add(text)
            missing.append(text)
        if not missing:
            return 0
        size = self._batch_size
        for start in range(0, len(missing), size):
            chunk = missing[start : start + size]
            vectors = self._embed_many(chunk)
            for text, vector in zip(chunk, vectors, strict=True):
                self._cache[text] = vector
        logger.info(
            "librarian query embed prefetch: %d unique strings in %d call(s)",
            len(missing),
            (len(missing) + size - 1) // size,
        )
        return len(missing)

    def _embed_many(self, texts: List[str]) -> List[List[float]]:
        try:
            raw = self._embed_fn(texts)
        except TypeError:
            logger.debug("embed_fn rejected a list; falling back to single calls")
            return [_as_vector(self._embed_fn(text)) for text in texts]
        if _is_vector(raw) or not isinstance(raw, (list, tuple)):
            raise TypeError(
                "embed_fn returned one vector for a list of texts; "
                "batch prefetch needs one vector per text"
            )
        vectors = [_as_vector(item) for item in raw]
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"embed_fn returned {len(vectors)} vectors for {len(texts)} texts"
            )
        return vectors


def install_query_embed_cache(root: object) -> Optional["QueryEmbedCache"]:
    """Point every nested ``_embed_fn`` at one cache per distinct function.

    Returns the cache when every retriever shared one embed function, which is
    how ``build_components`` wires the live pipeline. A second call returns the
    cache already installed, so each queue batch can prefetch into it. Returns
    None when the tree has no embed function (hermetic stubs).
    """
    found: List[tuple[object, EmbedFn]] = []
    existing: List[QueryEmbedCache] = []
    seen: set[int] = set()

    def walk(obj: object) -> None:
        if obj is None or id(obj) in seen:
            return
        seen.add(id(obj))
        fn = getattr(obj, "_embed_fn", None)
        if isinstance(fn, QueryEmbedCache):
            if fn not in existing:
                existing.append(fn)
        elif callable(fn):
            found.append((obj, fn))
        for attr in _CHILD_ATTRS:
            child = getattr(obj, attr, None)
            if child is not None:
                walk(child)

    walk(root)

    by_fn: Dict[int, List[tuple[object, EmbedFn]]] = {}
    for obj, fn in found:
        by_fn.setdefault(id(fn), []).append((obj, fn))

    caches: List[QueryEmbedCache] = list(existing)
    for pairs in by_fn.values():
        cache = QueryEmbedCache(pairs[0][1])
        for obj, _fn in pairs:
            setattr(obj, "_embed_fn", cache)
        caches.append(cache)
    if not caches:
        return None
    return caches[0]


def _installed_caches(root: object) -> List[QueryEmbedCache]:
    found: List[QueryEmbedCache] = []
    seen: set[int] = set()

    def walk(obj: object) -> None:
        if obj is None or id(obj) in seen:
            return
        seen.add(id(obj))
        fn = getattr(obj, "_embed_fn", None)
        if isinstance(fn, QueryEmbedCache) and fn not in found:
            found.append(fn)
        for attr in _CHILD_ATTRS:
            child = getattr(obj, attr, None)
            if child is not None:
                walk(child)

    walk(root)
    return found


def prefetch_retriever_embeddings(retriever: object, texts: Sequence[str]) -> int:
    """Install the cache and prefetch when batching is enabled.

    Returns the number of newly embedded strings, or 0 when disabled or the
    retriever has no embed function. Distinct embed functions are each
    prefetched; a shared cache is filled once.
    """
    if not embed_batch_enabled():
        return 0
    if install_query_embed_cache(retriever) is None:
        return 0
    total = 0
    filled: set[int] = set()
    for cache in _installed_caches(retriever):
        if id(cache) in filled:
            continue
        filled.add(id(cache))
        total += cache.prefetch(texts)
    return total


def _is_vector(raw: object) -> bool:
    if not isinstance(raw, (list, tuple)) or not raw:
        return False
    return isinstance(raw[0], (int, float))


def _as_vector(raw: object) -> List[float]:
    if not isinstance(raw, (list, tuple)):
        raise TypeError(
            f"embedding must be a sequence of floats, got {type(raw).__name__}"
        )
    return [float(x) for x in raw]
