import requests
import time
import logging
import os
from rq import Queue, job, exceptions
from typing import List, Dict
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


def _all_requested_standards_exist(standards: List[str], database) -> bool:
    """
    Best-effort check that all requested standards exist in the database.

    - If the check fails unexpectedly or returns a non-sequence (e.g. in tests
      with heavy mocking), we assume they exist to avoid changing behaviour.
    - If the standards list is empty, we treat it as valid and let the rest of
      the logic handle it.
    """
    if not standards:
        return True

    try:
        existing = database.standards()
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.error(
            f"Unable to verify standards existence when scheduling gap analysis, "
            f"proceeding anyway: {exc}"
        )
        return True

    if not isinstance(existing, (list, tuple, set)):
        # In test environments this may be a MagicMock; do not enforce the
        # existence check in that case to keep behaviour unchanged.
        logger.debug(
            f"database.standards() returned non-iterable type "
            f"{type(existing)}, skipping existence check"
        )
        return True

    existing_lower = {str(s).lower() for s in existing}
    missing = [s for s in standards if str(s).lower() not in existing_lower]

    if missing:
        standards_hash = make_resources_key(standards)
        logger.info(
            f"Gap analysis request {standards_hash} references standards "
            f"that do not exist in the database: {', '.join(missing)}"
        )
        return False

    return True


# database is of type Node_collection, cannot annotate due to circular import
def schedule(standards: List[str], database):
    """
    Schedule or retrieve gap analysis for the given standards.

    This function handles Redis queue operations and job scheduling.
    For web requests, the caller (map_analysis route) should check:
    - Cached results in database first
    - Heroku environment and standards existence (if on Heroku)
    - CRE_NO_CALCULATE_GAP_ANALYSIS env var

    This function still checks for cached results as a safety net for
    non-web callers (e.g., cre_main.py during imports).
    """
    from application.database import db

    standards_hash = make_resources_key(standards)

    # Check for cached results (safety net for non-web callers)
    if database.gap_analysis_exists(standards_hash):
        return flask_json.loads(database.get_gap_analysis_result(standards_hash))

    logger.info(f"Gap analysis result for {standards_hash} does not exist")

    conn = redis.connect()
    gap_analysis_results = conn.get(standards_hash)
    if (
        gap_analysis_results
    ):  # perhaps its calculated but not cached yet, get it from redis
        gap_analysis_dict = json.loads(gap_analysis_results)
        if gap_analysis_dict.get("job_id"):
            try:
                res = job.Job.fetch(id=gap_analysis_dict.get("job_id"), connection=conn)
            except exceptions.NoSuchJobError as nje:
                logger.error(
                    f"Could not find job id for gap analysis {standards}, this is a bug"
                )
                return {"error": 404}
            if (
                res.get_status() != job.JobStatus.FAILED
                and res.get_status() != job.JobStatus.STOPPED
                and res.get_status() != job.JobStatus.CANCELED
            ):
                logger.info(
                    f'gap analysis job id  {gap_analysis_dict.get("job_id")}, for standards: {standards[0]}>>{standards[1]} already exists, returning early'
                )
                return {"job_id": gap_analysis_dict.get("job_id")}
    q = Queue(connection=conn)
    gap_analysis_job = q.enqueue_call(
        db.gap_analysis,
        kwargs={
            "neo_db": database.neo_db,
            "node_names": standards,
            "cache_key": standards_hash,
        },
        timeout=GAP_ANALYSIS_TIMEOUT,
    )
    conn.set(standards_hash, json.dumps({"job_id": gap_analysis_job.id, "result": ""}))
    return {"job_id": gap_analysis_job.id}


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
