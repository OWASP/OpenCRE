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
OPENCRE_STANDARD_NAME = "OpenCRE"
OPENCRE_OVERLAP_LINK_TYPES = (
    defs.LinkTypes.LinkedTo,
    defs.LinkTypes.AutomaticallyLinkedTo,
)


def make_resources_key(array: List[str]):
    return " >> ".join(array)


def make_subresources_key(standards: List[str], key: str) -> str:
    return str(make_resources_key(standards)) + "->" + key


def gap_analysis_cache_key_is_primary(cache_key: str) -> bool:
    """Primary directed-standard rows use ``A >> B``; drill-down rows append ``->...``."""
    marker = " >> "
    idx = cache_key.find(marker)
    if idx < 0:
        return False
    # Subresource keys are ``A >> B->nodeKey``; only inspect text after the pair.
    suffix = cache_key[idx + len(marker) :]
    return "->" not in suffix


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


def should_persist_primary_gap_analysis_cache(
    ga_object: str,
    existing_ga_object: Optional[str] = None,
) -> bool:
    """
    True when a primary GA SQL cache write should be applied.

    Non-material empty ``{"result": {}}`` payloads must not be inserted and must
    not overwrite an existing material row.
    """
    if primary_gap_analysis_payload_is_material(ga_object):
        return True
    if existing_ga_object is None:
        return False
    if primary_gap_analysis_payload_is_material(existing_ga_object):
        return False
    return False


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


def _link_type_to_path_relationship(ltype: defs.LinkTypes) -> str:
    """Map a link type to the path relationship label stored in GA cache rows."""
    if ltype == defs.LinkTypes.AutomaticallyLinkedTo:
        return "AUTOMATICALLY_LINKED_TO"
    return "LINKED_TO"


def _opencre_overlap_link_sort_key(link: defs.Link) -> int:
    """Prefer manual CRE links over automatic links when ordering overlap paths."""
    if link.ltype == defs.LinkTypes.LinkedTo:
        return 0
    if link.ltype == defs.LinkTypes.AutomaticallyLinkedTo:
        return 1
    return 2


def _build_direct_link_path(
    start_document: defs.Document,
    end_document: defs.Document,
    *,
    ltype: defs.LinkTypes = defs.LinkTypes.LinkedTo,
) -> Dict[str, Any]:
    """Build a single-hop GA path between two documents with the given link type."""
    segment_start = start_document.shallow_copy()
    if segment_start.doctype != defs.Credoctypes.CRE.value:
        segment_start.id = ""
    return {
        "end": end_document.shallow_copy(),
        "path": [
            {
                "start": segment_start,
                "end": end_document.shallow_copy(),
                "relationship": _link_type_to_path_relationship(ltype),
                "score": 0,
            }
        ],
        "score": 0,
    }


def _add_direct_link_result(
    grouped_paths: Dict[str, Dict[str, Any]],
    start_document: defs.Document,
    end_document: defs.Document,
    *,
    ltype: defs.LinkTypes = defs.LinkTypes.LinkedTo,
) -> None:
    """Insert one direct link path into grouped GA results, skipping duplicates."""
    shared_paths = grouped_paths.setdefault(
        start_document.id,
        {
            "start": start_document.shallow_copy(),
            "paths": {},
            "extra": 0,
        },
    )["paths"]
    path_key = end_document.id
    if path_key in shared_paths:
        return
    shared_paths[path_key] = _build_direct_link_path(
        start_document, end_document, ltype=ltype
    )


def build_direct_cre_overlap_map_analysis(
    standards: List[str],
    standards_hash: str,
    collection: Any,
) -> Optional[Dict[str, Any]]:
    """Compute one-step OpenCRE links (manual and automatic) for a standard pair."""
    if len(standards) < 2:
        return None

    base_standard = standards[0]
    compare_standard = standards[1]
    base_is_opencre = base_standard == OPENCRE_STANDARD_NAME
    compare_is_opencre = compare_standard == OPENCRE_STANDARD_NAME
    if not base_is_opencre and not compare_is_opencre:
        return None

    standard_name = compare_standard if base_is_opencre else base_standard
    standard_nodes = collection.get_nodes(name=standard_name)
    if not standard_nodes:
        return None

    grouped_paths: Dict[str, Dict[str, Any]] = {}
    for standard_node in standard_nodes:
        cre_links = [
            link
            for link in (standard_node.links or [])
            if link.ltype in OPENCRE_OVERLAP_LINK_TYPES
            and link.document.doctype == defs.Credoctypes.CRE.value
        ]
        for link in sorted(cre_links, key=_opencre_overlap_link_sort_key):
            linked_document = link.document
            if base_is_opencre:
                _add_direct_link_result(
                    grouped_paths,
                    linked_document,
                    standard_node,
                    ltype=link.ltype,
                )
            else:
                _add_direct_link_result(
                    grouped_paths,
                    standard_node,
                    linked_document,
                    ltype=link.ltype,
                )

    if not grouped_paths:
        return None

    result = {"result": grouped_paths}
    collection.add_gap_analysis_result(
        cache_key=standards_hash, ga_object=flask_json.dumps(result)
    )
    return result


def opencre_direct_pairs(standard_names: List[str]) -> List[List[str]]:
    """Directed OpenCRE pairs for every real standard name."""
    pairs: List[List[str]] = []
    for name in sorted({str(s).strip() for s in standard_names if str(s).strip()}):
        if name == OPENCRE_STANDARD_NAME:
            continue
        pairs.append([OPENCRE_STANDARD_NAME, name])
        pairs.append([name, OPENCRE_STANDARD_NAME])
    return pairs


def missing_opencre_direct_pairs(collection: Any) -> List[List[str]]:
    """Return OpenCRE-directed standard pairs that are not yet cached."""
    missing: List[List[str]] = []
    for pair in opencre_direct_pairs(collection.standards()):
        cache_key = make_resources_key(pair)
        if not collection.gap_analysis_exists(cache_key):
            missing.append(pair)
    return missing


def backfill_opencre_direct_pairs(collection: Any, *, refresh: bool = False) -> int:
    """Populate SQL cache rows for OpenCRE map analysis pairs (manual + automatic links)."""
    pairs = opencre_direct_pairs(collection.standards())
    if refresh:
        todo = pairs
        logger.info("OpenCRE direct GA backfill: refreshing all pairs=%s", len(todo))
    else:
        todo = missing_opencre_direct_pairs(collection)
        if not todo:
            logger.info("OpenCRE direct GA backfill: no missing pairs")
            return 0
        logger.info("OpenCRE direct GA backfill: missing_pairs=%s", len(todo))

    written = 0
    for pair in todo:
        cache_key = make_resources_key(pair)
        if build_direct_cre_overlap_map_analysis(pair, cache_key, collection):
            written += 1
    logger.info(
        "OpenCRE direct GA backfill: wrote=%s remaining=%s",
        written,
        len(missing_opencre_direct_pairs(collection)),
    )
    return written


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
            waiting.append((sa, sb))

    MAX_RETRIES = 10
    retries = {pair: 0 for pair in waiting}

    while len(waiting):
        for pair in list(waiting):
            sa, sb = pair
            if calculate_a_to_b(sa, sb):
                waiting.remove(pair)
            else:
                retries[pair] += 1
                if retries[pair] >= MAX_RETRIES:
                    print(
                        f"{sa}->{sb} reached max retries ({MAX_RETRIES}), dropping from waiting list"
                    )
                    waiting.remove(pair)

        if waiting:
            print(f"calculating {len(waiting)} gap analyses")
            time.sleep(30)
    print("map analysis preloaded successfully")
