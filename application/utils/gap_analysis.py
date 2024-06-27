import requests
import time
import logging
from rq import Queue, job, exceptions
from typing import List, Dict
from application.utils import redis
from application.database import db
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


# database is of type Node_collection, cannot annotate due to circular import
def schedule(standards: List[str], database):
    conn = redis.connect()
    standards_hash = make_resources_key(standards)
    if database.gap_analysis_exists(
        standards_hash
    ):  # easiest, it's been calculated and cached, get it from the db
        return flask_json.loads(database.get_gap_analysis_result(standards_hash))

    logger.info(f"Gap analysis result for {standards_hash} does not exist")
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
