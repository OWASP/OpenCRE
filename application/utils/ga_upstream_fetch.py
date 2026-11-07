"""Opportunistic gap analysis fetch from an upstream OpenCRE instance.

A local instance can resolve a missing primary pair (``A >> B``) by pulling the
precomputed row from production instead of computing it, see
``docs/rfc/local-ga-opportunistic-fetch.md``. Callers keep the Heroku cache-only
guard: this module must not run on production.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

import requests

from application.feature_flags import is_ga_upstream_disabled
from application.utils import gap_analysis, redis

if TYPE_CHECKING:
    from application.database import db

DEFAULT_UPSTREAM_API_URL = "https://opencre.org/rest/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0

# Separate from the ``ga:inflight:`` namespace used by the RQ compute jobs.
INFLIGHT_KEY_PREFIX = "ga:upstream:inflight:"
INFLIGHT_LOCK_BUFFER_SECONDS = 30
POLL_AFTER_SECONDS = 2

BACKFILL_DOCS_URL = (
    "https://github.com/OWASP/OpenCRE/blob/main/AGENTS.md"
    "#gap-analysis-local-compute-prod-verify"
)
NEW_ISSUE_URL = "https://github.com/OWASP/OpenCRE/issues/new"

ERROR_CACHE_MISS = "ga_cache_miss"
ERROR_UPSTREAM_UNAVAILABLE = "ga_upstream_unavailable"

# Fallback lock for instances without Redis; only covers a single worker process.
_local_inflight: Set[str] = set()
_local_inflight_guard = threading.Lock()


class GaUpstreamError(Exception):
    """The upstream could not provide an answer, it may succeed later."""


class GaUpstreamNotFound(GaUpstreamError):
    """The upstream answered definitively: it does not have this resource."""


@dataclass(frozen=True)
class GaUpstreamSettings:
    base_url: str
    timeout_seconds: float
    max_attempts: int
    backoff_seconds: float

    @property
    def inflight_lock_ttl_seconds(self) -> int:
        """Outlives a full fetch: every attempt and every wait is capped by the timeout."""
        worst_case = (2 * self.max_attempts - 1) * self.timeout_seconds
        return int(worst_case) + INFLIGHT_LOCK_BUFFER_SECONDS


@dataclass(frozen=True)
class GapAnalysisResolution:
    """HTTP status and JSON body a caller should answer a pair request with."""

    status_code: int
    payload: Dict[str, Any]


def _number_from_env(
    name: str, default: Any, minimum: float, cast: Callable[[str], Any]
) -> Any:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw)
    except ValueError:
        value = None
    if value is None or not minimum <= value < float("inf"):
        logger.warning("Ignoring invalid %s=%r, using %s", name, raw, default)
        return default
    return value


def load_settings() -> GaUpstreamSettings:
    base_url = os.environ.get("CRE_GA_UPSTREAM_API_URL") or DEFAULT_UPSTREAM_API_URL
    return GaUpstreamSettings(
        base_url=base_url.rstrip("/"),
        timeout_seconds=_number_from_env(
            "CRE_GA_UPSTREAM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, 1, float
        ),
        max_attempts=_number_from_env(
            "CRE_GA_UPSTREAM_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS, 1, int
        ),
        backoff_seconds=_number_from_env(
            "CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS",
            DEFAULT_RETRY_BACKOFF_SECONDS,
            0,
            float,
        ),
    )


def _retry_delay_seconds(
    response: Optional[requests.Response],
    attempt: int,
    settings: GaUpstreamSettings,
) -> float:
    delay = settings.backoff_seconds * attempt
    if response is not None and response.status_code == 429:
        try:
            delay = float(response.headers.get("Retry-After", delay))
        except (TypeError, ValueError):
            pass
    # The caller's HTTP request is waiting on this: never sleep past the timeout.
    return max(0.0, min(delay, settings.timeout_seconds))


def fetch_ga_upstream_json(
    path: str,
    params: Optional[List[Tuple[str, str]]] = None,
    settings: Optional[GaUpstreamSettings] = None,
) -> Dict[str, Any]:
    """
    GET ``path`` from the upstream REST API, with the retry semantics of
    ``cre_main.fetch_upstream_json``: network errors, ``5xx`` and ``429`` are
    retried, ``404`` and other ``4xx`` are not.

    Raises GaUpstreamNotFound on ``404`` and GaUpstreamError on any other failure.
    """
    settings = settings or load_settings()
    url = f"{settings.base_url}{path}"
    last_error: Optional[Exception] = None

    for attempt in range(1, settings.max_attempts + 1):
        response = None
        try:
            response = requests.get(
                url, params=params, timeout=settings.timeout_seconds
            )
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise GaUpstreamError(f"unexpected upstream payload from {url}")
            if response.status_code == 404:
                raise GaUpstreamNotFound(f"upstream has no resource at {url}")
            status_error = GaUpstreamError(
                f"upstream status code {response.status_code} from {url}"
            )
            if response.status_code < 500 and response.status_code != 429:
                raise status_error
            last_error = status_error
        except requests.exceptions.RequestException as exc:
            last_error = exc

        if attempt < settings.max_attempts:
            logger.warning(
                "GA upstream fetch failed for %s on attempt %s/%s, retrying",
                url,
                attempt,
                settings.max_attempts,
            )
            time.sleep(_retry_delay_seconds(response, attempt, settings))

    raise GaUpstreamError(f"GA upstream fetch failed for {url}") from last_error


def _acquire_local_lock(key: str) -> Optional[Callable[[], None]]:
    with _local_inflight_guard:
        if key in _local_inflight:
            return None
        _local_inflight.add(key)

    def release() -> None:
        with _local_inflight_guard:
            _local_inflight.discard(key)

    return release


def _acquire_inflight_lock(
    cache_key: str, ttl_seconds: int
) -> Optional[Callable[[], None]]:
    """Return a release callback, or None when another fetch holds this pair."""
    key = f"{INFLIGHT_KEY_PREFIX}{cache_key}"
    try:
        conn = redis.connect()
        if not conn.set(key, "1", nx=True, ex=ttl_seconds):
            return None
    except Exception as exc:
        logger.warning(
            "Redis unavailable for GA upstream lock on %s; using a local lock: %s",
            cache_key,
            exc,
        )
        return _acquire_local_lock(key)

    def release() -> None:
        try:
            conn.delete(key)
        except Exception as exc:
            logger.warning(
                "Could not release GA upstream lock on %s, it expires in %ss: %s",
                cache_key,
                ttl_seconds,
                exc,
            )

    return release


def _cached_result(database: db.Node_collection, cache_key: str) -> Optional[Any]:
    if not database.gap_analysis_exists(cache_key):
        return None
    cached = database.get_gap_analysis_result(cache_key=cache_key)
    return json.loads(cached).get("result")


def _soft_cta(standards: List[str], database: db.Node_collection) -> Dict[str, Any]:
    """Invite an issue report only when both standards should have this pair."""
    # Deferred like the ga_standards route: cre_main pulls in the whole import stack.
    from application.cmd import cre_main

    if not all(
        cre_main.resource_name_ga_eligible_in_db(database, standard)
        for standard in standards
    ):
        return {"show": False}
    return {
        "show": True,
        "message": (
            "Both standards appear valid for gap analysis but this pair could not "
            "be fetched from the upstream OpenCRE instance. Consider filing an issue."
        ),
        "issue_url": NEW_ISSUE_URL,
    }


def _success(result: Any) -> GapAnalysisResolution:
    return GapAnalysisResolution(200, {"result": result})


def _in_progress(cache_key: str) -> GapAnalysisResolution:
    return GapAnalysisResolution(
        202,
        {
            "status": "in_progress",
            "cache_key": cache_key,
            "poll_after_seconds": POLL_AFTER_SECONDS,
        },
    )


def _cache_miss(message: str, soft_cta: Dict[str, Any]) -> GapAnalysisResolution:
    return GapAnalysisResolution(
        404,
        {
            "error_code": ERROR_CACHE_MISS,
            "message": message,
            "try_again": False,
            "backfill_docs_url": BACKFILL_DOCS_URL,
            "soft_cta": soft_cta,
        },
    )


def _upstream_unavailable(soft_cta: Dict[str, Any]) -> GapAnalysisResolution:
    return GapAnalysisResolution(
        503,
        {
            "error_code": ERROR_UPSTREAM_UNAVAILABLE,
            "message": (
                "Could not reach the upstream OpenCRE instance to fetch this gap "
                "analysis."
            ),
            "try_again": True,
            "backfill_docs_url": BACKFILL_DOCS_URL,
            "soft_cta": soft_cta,
        },
    )


def _fetch_and_store_pair(
    standards: List[str],
    cache_key: str,
    database: db.Node_collection,
    settings: GaUpstreamSettings,
) -> Any:
    """Pull one pair from upstream and upsert it; a bad answer never reaches the DB."""
    payload = fetch_ga_upstream_json(
        "/map_analysis",
        params=[("standard", standard) for standard in standards],
        settings=settings,
    )
    result = payload.get("result")
    ga_object = json.dumps({"result": result})
    if not gap_analysis.primary_gap_analysis_payload_is_material(ga_object):
        raise GaUpstreamError(f"upstream has no material result for {cache_key}")
    database.add_gap_analysis_result(cache_key=cache_key, ga_object=ga_object)
    logger.info(
        "GA upstream fetch: pulled pair %s from %s", cache_key, settings.base_url
    )
    return result


def resolve_gap_analysis_pair(
    standards: List[str], database: db.Node_collection
) -> GapAnalysisResolution:
    """
    Serve a primary pair from the local cache, or fetch and cache it from upstream.

    Once cached a pair is always served locally. A fetch runs in the calling
    request; concurrent requests for the same pair get ``in_progress`` and should
    poll. Nothing here computes gap analysis or falls back to doing so.
    """
    cache_key = gap_analysis.make_resources_key(standards)

    cached = _cached_result(database, cache_key)
    if cached is not None:
        return _success(cached)

    if is_ga_upstream_disabled():
        return _cache_miss(
            "This gap analysis pair is not cached locally and fetching it from "
            "upstream is disabled by CRE_GA_NO_UPSTREAM.",
            {"show": False},
        )

    settings = load_settings()
    release_lock = _acquire_inflight_lock(cache_key, settings.inflight_lock_ttl_seconds)
    if release_lock is None:
        return _in_progress(cache_key)

    try:
        # A fetch may have finished between the check above and taking the lock.
        cached = _cached_result(database, cache_key)
        if cached is not None:
            return _success(cached)
        return _success(_fetch_and_store_pair(standards, cache_key, database, settings))
    except GaUpstreamNotFound:
        return _cache_miss(
            "This gap analysis pair is not cached locally or on the upstream "
            "OpenCRE instance.",
            _soft_cta(standards, database),
        )
    except GaUpstreamError as exc:
        logger.warning("GA upstream fetch failed for %s: %s", cache_key, exc)
        # A backfill or sync may have written the row while the fetch was failing.
        cached = _cached_result(database, cache_key)
        if cached is not None:
            return _success(cached)
        return _upstream_unavailable(_soft_cta(standards, database))
    finally:
        release_lock()
