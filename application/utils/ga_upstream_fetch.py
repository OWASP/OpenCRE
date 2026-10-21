from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
from cre_logging import get_logger

from application.database import db
from application.defs import cre_defs as defs
from application.utils import gap_analysis

logger = get_logger(__name__)

DEFAULT_UPSTREAM_API_URL = "https://opencre.org/rest/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
BACKFILL_DOCS_URL = (
    "https://github.com/OWASP/OpenCRE/blob/main/docs/backfill_gap_analysis.md"
)
GITHUB_NEW_ISSUE_URL = "https://github.com/OWASP/OpenCRE/issues/new"

_IN_PROCESS_LOCK = threading.Lock()
_IN_FLIGHT_KEYS: set[str] = set()


def is_ga_upstream_disabled() -> bool:
    """Return True if CRE_GA_NO_UPSTREAM is set to 1, true, or yes (case-insensitive)."""
    val = os.environ.get("CRE_GA_NO_UPSTREAM", "").strip().lower()
    return val in ("1", "true", "yes")


def _acquire_inflight_lock(cache_key: str, ttl: int = 150) -> bool:
    """Acquire an in-flight lock for cache_key. Return True if acquired, False if already in-flight."""
    try:
        from application.database import redis as cre_redis

        conn = cre_redis.connect()
        lock_key = f"ga:upstream:inflight:{cache_key}"
        res = conn.set(lock_key, "1", ex=ttl, nx=True)
        if res:
            return True
        return False
    except Exception:
        with _IN_PROCESS_LOCK:
            if cache_key in _IN_FLIGHT_KEYS:
                return False
            _IN_FLIGHT_KEYS.add(cache_key)
            return True


def _release_inflight_lock(cache_key: str) -> None:
    """Release the in-flight lock for cache_key."""
    try:
        from application.database import redis as cre_redis

        conn = cre_redis.connect()
        lock_key = f"ga:upstream:inflight:{cache_key}"
        conn.delete(lock_key)
    except Exception:
        pass
    with _IN_PROCESS_LOCK:
        _IN_FLIGHT_KEYS.discard(cache_key)


def fetch_ga_upstream_json(
    standards: List[str],
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_attempts: Optional[int] = None,
    backoff_seconds: Optional[float] = None,
    session: Optional[Any] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[Exception]]:
    """
    Fetch GA pair from upstream prod with retries matching D12 / RFC #951 pattern.
    Read-only GET requests, no auth headers.
    Returns: (payload_dict, status_code, exception)
    """
    if len(standards) < 2:
        raise ValueError("Must provide at least two standards")

    base = (
        base_url
        or os.environ.get("CRE_GA_UPSTREAM_API_URL", DEFAULT_UPSTREAM_API_URL)
    ).rstrip("/")
    req_timeout = timeout or float(
        os.environ.get(
            "CRE_GA_UPSTREAM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)
        )
    )
    attempts = max_attempts or int(
        os.environ.get(
            "CRE_GA_UPSTREAM_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS)
        )
    )
    backoff = backoff_seconds or float(
        os.environ.get(
            "CRE_GA_UPSTREAM_RETRY_BACKOFF_SECONDS",
            str(DEFAULT_RETRY_BACKOFF_SECONDS),
        )
    )

    params = [("standard", standards[0]), ("standard", standards[1])]
    query_string = urllib.parse.urlencode(params)
    url = f"{base}/map_analysis?{query_string}"

    http = session or requests
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None

    for attempt in range(1, attempts + 1):
        resp = None
        try:
            resp = http.get(url, timeout=req_timeout)
            last_status = resp.status_code
            if last_status == 200:
                return resp.json(), 200, None
            if last_status == 404:
                # D12: Do not retry 404
                return None, 404, None
            if last_status < 500 and last_status != 429:
                # Other 4xx errors are terminal (do not retry)
                return (
                    None,
                    last_status,
                    RuntimeError(f"Upstream returned HTTP {last_status}"),
                )
            # 429 or 5xx -> retry
            last_exc = RuntimeError(f"Upstream returned HTTP {last_status}")
        except requests.exceptions.RequestException as exc:
            last_exc = exc

        if attempt < attempts:
            sleep_time = backoff * attempt
            if resp is not None and resp.status_code == 429:
                hdr = resp.headers.get("Retry-After")
                try:
                    if hdr:
                        sleep_time = float(hdr)
                except (TypeError, ValueError):
                    pass
            logger.warning(
                "GA upstream fetch failed for %s on attempt %s/%s, retrying",
                url,
                attempt,
                attempts,
            )
            time.sleep(sleep_time)

    return None, last_status, last_exc


def _evaluate_soft_cta(standards: List[str], database: Any) -> Dict[str, Any]:
    """
    Check D7 soft CTA conditions:
    1) Both standards exist locally in CRE graph
    2) Both are valid GA participants
    3) Upstream map_analysis exhausted with 404
    """
    try:
        std_a, std_b = standards[0], standards[1]
        node_a = database.get_node(name=std_a, ntype=defs.Standard.__name__)
        node_b = database.get_node(name=std_b, ntype=defs.Standard.__name__)
        if not node_a or not node_b:
            return {"show": False}

        ga_stds: List[str] = []
        if hasattr(database, "get_ga_standards"):
            ga_stds = database.get_ga_standards()
        elif hasattr(database, "get_standards"):
            ga_stds = [s.name for s in database.get_standards()]

        if ga_stds and (std_a not in ga_stds or std_b not in ga_stds):
            return {"show": False}

        return {
            "show": True,
            "message": "Both standards appear valid for gap analysis but this pair is missing from opencre.org. Consider filing an issue.",
            "issue_url": GITHUB_NEW_ISSUE_URL,
        }
    except Exception as ex:
        logger.debug("Error checking soft CTA: %s", ex)
        return {"show": False}


def resolve_gap_analysis_pair(
    standards: List[str],
    database: db.Node_collection,
    session: Optional[Any] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Single shared backend resolver for local gap analysis on-demand fetch (D1, D2, D3, D4, D5, D7):
    1. Local cache hit: return cached row if material (V1 no re-fetch).
    2. CRE_GA_NO_UPSTREAM: return 404 + backfill instructions (no prod HTTP).
    3. In-flight lock: return 202 in_progress if another request is already fetching this pair.
    4. Fetch from upstream prod (opencre.org):
       - 200: upsert material payload locally into gap_analysis_results, return 200.
       - 404: check D7 soft CTA, return 404 + backfill docs.
       - Exhausted retries / unreachable: return local cached row if present; else 503 try_again.
    """
    if len(standards) < 2:
        return 400, {"message": "Please provide two standards"}
    standards = standards[:2]
    cache_key = gap_analysis.make_resources_key(standards)

    # 1. Local cache check
    if database.gap_analysis_exists(cache_key):
        cached = database.get_gap_analysis_result(cache_key=cache_key)
        if cached:
            try:
                parsed = json.loads(cached)
                res = parsed.get("result", parsed)
                if gap_analysis.primary_gap_analysis_payload_is_material(res):
                    return 200, {"result": res}
            except Exception:
                pass

    # 2. Disabled check
    if is_ga_upstream_disabled():
        return 404, {
            "error_code": "ga_cache_miss",
            "message": "This gap analysis pair is not cached locally or on opencre.org.",
            "backfill_docs_url": BACKFILL_DOCS_URL,
            "try_again": False,
        }

    # 3. In-flight lock check
    acquired = _acquire_inflight_lock(cache_key)
    if not acquired:
        return 202, {
            "status": "in_progress",
            "cache_key": cache_key,
            "poll_after_seconds": 2,
        }

    base_url = (
        os.environ.get("CRE_GA_UPSTREAM_API_URL", DEFAULT_UPSTREAM_API_URL)
    ).rstrip("/")
    try:
        payload, status_code, exc = fetch_ga_upstream_json(
            standards,
            base_url=base_url,
            session=session,
        )

        if status_code == 200 and payload:
            result_data = payload.get("result", payload)
            if gap_analysis.primary_gap_analysis_payload_is_material(
                result_data
            ):
                database.add_gap_analysis_result(
                    cache_key=cache_key,
                    ga_object=json.dumps({"result": result_data}),
                )
                logger.info(
                    "GA upstream fetch: pulled pair %s from %s",
                    cache_key,
                    base_url,
                )
                return 200, {"result": result_data}

        if status_code == 404:
            soft_cta = _evaluate_soft_cta(standards, database)
            resp_body: Dict[str, Any] = {
                "error_code": "ga_cache_miss",
                "message": "This gap analysis pair is not cached locally or on opencre.org.",
                "backfill_docs_url": BACKFILL_DOCS_URL,
                "try_again": False,
            }
            if soft_cta.get("show"):
                resp_body["soft_cta"] = soft_cta
            return 404, resp_body

        # Unreachable or exhausted retries: serve local row if available
        if database.gap_analysis_exists(cache_key):
            cached = database.get_gap_analysis_result(cache_key=cache_key)
            if cached:
                try:
                    parsed = json.loads(cached)
                    if "result" in parsed:
                        return 200, {"result": parsed.get("result")}
                except Exception:
                    pass

        return 503, {
            "error_code": "ga_upstream_unavailable",
            "message": "Could not reach opencre.org to fetch this gap analysis.",
            "backfill_docs_url": BACKFILL_DOCS_URL,
            "try_again": True,
        }
    finally:
        _release_inflight_lock(cache_key)
