import requests
import time
import logging
from rq import Queue, job, exceptions
from typing import List, Dict
from application.utils import redis
from application.utils.hash import make_array_hash, make_cache_key
from application.database import db
from flask import json as flask_json
import json

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PENALTIES = {
    "RELATED": 2,
    "CONTAINS_UP": 2,
    "CONTAINS_DOWN": 1,
    "LINKED_TO": 0,
    "SAME": 0,
}


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


def schedule(standards: List[str], database):
    conn = redis.connect()
    standards_hash = make_array_hash(standards)
    result = database.get_gap_analysis_result(standards_hash)
    if result:
        return flask_json.loads(result)

    gap_analysis_results = conn.get(standards_hash)
    if gap_analysis_results:
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
                logger.info("gap analysis job id already exists, returning early")
                return {"job_id": gap_analysis_dict.get("job_id")}
    q = Queue(connection=conn)
    gap_analysis_job = q.enqueue_call(
        db.gap_analysis,
        kwargs={
            "neo_db": database.neo_db,
            "node_names": standards,
            "store_in_cache": True,
            "cache_key": standards_hash,
        },
        timeout="10m",
    )
    conn.set(standards_hash, json.dumps({"job_id": gap_analysis_job.id, "result": ""}))
    return {"job_id": gap_analysis_job.id}


def preload(target_url: str):
    waiting = []
    standards_request = requests.get(f"{target_url}/rest/v1/standards")
    standards = standards_request.json()

    for sa in standards:
        for sb in standards:
            if sa == sb:
                continue
            waiting.append(f"{sa}->{sb}")
            waiting.append(f"{sb}->{sa}")
    while len(waiting):
        for sa in standards:
            for sb in standards:
                if sa == sb:
                    continue
                res1 = requests.get(
                    f"{target_url}/rest/v1/map_analysis?standard={sa}&standard={sb}"
                )
                if res1.status_code != 200:
                    print(f"{sa}->{sb} returned {res1.status_code}")
                elif res1.json():
                    if res1.json().get("result"):
                        if f"{sa}->{sb}" in waiting:
                            waiting.remove(f"{sa}->{sb}")
                res2 = requests.get(
                    f"{target_url}/rest/v1/map_analysis?standard={sb}&standard={sa}"
                )
                if res2.status_code != 200:
                    print(f"{sb}->{sa} returned {res1.status_code}")
                elif res2.json():
                    if res2.json().get("result"):
                        if f"{sb}->{sa}" in waiting:
                            waiting.remove(f"{sb}->{sa}")
        print(f"calculating {len(waiting)} gap analyses")
        time.sleep(30)
    print("map analysis preloaded successfully")
