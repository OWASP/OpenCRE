import os
import requests
import time
import logging
from typing import Any, Dict, List, Optional
from application.utils import redis
from flask import json as flask_json
import json
from application.defs import cre_defs as defs

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PENALTIES = {
    "RELATED": 2,
    "CONTAINS_UP": 2,
    "CONTAINS_DOWN": 1,
    "LINKED_TO": 0,
    "AUTOMATICALLY_LINKED_TO": 0,
    "SAME": 0,
}

GAP_ANALYSIS_TIMEOUT = "129600s"  # 36 hours


def make_resources_key(array: List[str]):
    return " >> ".join(array)


def make_subresources_key(standards: List[str], key: str) -> str:
    return str(make_resources_key(standards)) + "->" + key


def gap_analysis_cache_key_is_primary(cache_key: str) -> bool:
    """Primary directed-standard rows use ``A >> B``; drill-down rows append ``->...``."""
    return "->" not in cache_key


def primary_gap_analysis_payload_is_material(ga_object: Optional[str]) -> bool:
    """
    True when a stored GA payload has a non-empty object at ``result`` (main cache rows).

    Empty ``{"result": {}}`` placeholders must not count as a cached gap analysis.
    """
    if not ga_object or not isinstance(ga_object, str):
        return False
    try:
        parsed = json.loads(ga_object)
    except json.JSONDecodeError:
        return False
    res = parsed.get("result")
    if res is None:
        return False
    if isinstance(res, dict):
        return len(res) > 0
    if isinstance(res, list):
        return len(res) > 0
    return bool(res)


def get_path_score(path):
    score = 0
    previous_id = path["start"].id
    for step in path["path"]:
        penalty_type = step["relationship"]

        if step["relationship"] == "CONTAINS":
            penalty_type = f"CONTAINS_{get_relation_direction(step, previous_id)}"
        pentalty = PENALTIES[penalty_type]
        score += pentalty
        step["score"] = pentalty
        previous_id = get_next_id(step, previous_id)
    return score


def get_relation_direction(step, previous_id):
    if step["start"].id == previous_id:
        return "UP"
    return "DOWN"


def get_next_id(step, previous_id):
    if step["start"].id == previous_id:
        return step["end"].id
    return step["start"].id


def perform(standards: List[str], database):
    return run_gap_pair(standards[0], standards[1], database)


def _backend_name_from_database(database: Any) -> str:
    try:
        bind = getattr(getattr(database, "session", None), "bind", None)
        if bind is None:
            return "unknown"
        url = getattr(bind, "url", None)
        if url is None:
            return "unknown"
        if hasattr(url, "get_backend_name"):
            return str(url.get_backend_name())
        return str(url).split("://", 1)[0].lower()
    except Exception:
        return "unknown"


def run_gap_pair(
    importing_name: str,
    peer_name: str,
    database: Any,
    *,
    require_postgres: bool = False,
    sleep_seconds: int = 10,
    max_compute_retries: int = 2,
):
    """Compute/fetch one directed GA pair with cache + Redis lock coordination."""
    from application.database import db

    backend_name = _backend_name_from_database(database)
    if require_postgres and backend_name not in ("postgresql", "postgres"):
        raise RuntimeError(
            f"Pair GA scheduling requires Postgres backend, got {backend_name or 'unknown'}"
        )

    standards = [importing_name, peer_name]
    standards_hash = make_resources_key(standards)

    # Fast path: cached in SQL, no Redis/lock needed.
    if database.gap_analysis_exists(standards_hash):
        res = database.get_gap_analysis_result(standards_hash)
        if res is None:
            return {"result": {}}
        return json.loads(res) if isinstance(res, str) else res

    conn = redis.connect()
    lock_key = f"lock:ga:{standards_hash}"
    attempts = 0

    def _is_transient_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        transient_markers = (
            "deadlock detected",
            "could not serialize access",
            "connection reset",
            "temporarily unavailable",
            "service unavailable",
            "timeout",
        )
        if any(m in msg for m in transient_markers):
            return True
        mod = exc.__class__.__module__.lower()
        return "neo4j" in mod or "redis" in mod

    while True:
        # Another process may have populated cache while we were waiting for lock.
        if database.gap_analysis_exists(standards_hash):
            res = database.get_gap_analysis_result(standards_hash)
            if res is None:
                return {"result": {}}
            return json.loads(res) if isinstance(res, str) else res

        acquired = conn.setnx(lock_key, "1")
        if acquired:
            conn.expire(lock_key, 129600)
            try:
                logger.info(f"Calculating gap analysis for {standards_hash}")
                db.gap_analysis(
                    neo_db=database.neo_db,
                    node_names=standards,
                    cache_key=standards_hash,
                )
                res = database.get_gap_analysis_result(standards_hash)
                if res is None:
                    return {"result": {}}
                return json.loads(res) if isinstance(res, str) else res
            except Exception as exc:
                attempts += 1
                if _is_transient_error(exc) and attempts <= max_compute_retries:
                    wait_s = int(os.environ.get("CRE_GA_RETRY_BACKOFF_SECONDS", "2"))
                    logger.warning(
                        "Transient GA error for %s (attempt %s/%s): %s",
                        standards_hash,
                        attempts,
                        max_compute_retries,
                        exc,
                    )
                    time.sleep(wait_s)
                    continue
                raise
            finally:
                conn.delete(lock_key)
        else:
            logger.info(
                f"Gap analysis for {standards_hash} is being calculated by another worker. Waiting..."
            )
            time.sleep(sleep_seconds)


def schedule(standards: List[str], database):
    res = perform(standards, database)
    # the api endpoint returns json.dumps({"result": ...}) or similar. Let's make it compatible.
    return {"result": res.get("result") if isinstance(res, dict) else res}


def preload(target_url: str):
    waiting = []
    standards_request = requests.get(f"{target_url}/rest/v1/standards")
    standards = standards_request.json()

    def calculate_a_to_b(sa: str, sb: str) -> bool:
        res = requests.get(
            f"{target_url}/rest/v1/map_analysis?standard={sa}&standard={sb}"
        )
        if res.status_code != 200:
            print(f"{sa}->{sb} returned {res.status_code}")
            return False

        tojson = res.json()
        if tojson.get("result"):
            return True
        if tojson.get("job_id"):
            print(f"{sa}->{sb} waiting")
            return False
        print(f"{sa}->{sb} returned 200 but has no 'result' or 'job_id' key")
        return False

    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            waiting.append(f"{sa}->{sb}")
    while len(waiting):
        for sa in standards:
            for sb in standards:
                if sa == sb:
                    continue
                if calculate_a_to_b(sa, sb):
                    waiting.remove(f"{sa}->{sb}") if f"{sa}->{sb}" in waiting else ""
        print(f"calculating {len(waiting)} gap analyses")
        time.sleep(30)
    print("map analysis preloaded successfully")
