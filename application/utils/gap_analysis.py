import requests
import time
import logging
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


def perform(standards: List[str], database):
    from application.database import db

    standards_hash = make_resources_key(standards)
    
    conn = redis.connect()
    lock_key = f"lock:ga:{standards_hash}"

    while True:
        if database.gap_analysis_exists(standards_hash):
            res = database.get_gap_analysis_result(standards_hash)
            return json.loads(res) if isinstance(res, str) else res

        acquired = conn.setnx(lock_key, "1")
        if acquired:
            conn.expire(lock_key, 129600)
            try:
                logger.info(f"Calculating gap analysis for {standards_hash}")
                db.gap_analysis(
                    neo_db=database.neo_db,
                    node_names=standards,
                    cache_key=standards_hash
                )
                res = database.get_gap_analysis_result(standards_hash)
                return json.loads(res) if isinstance(res, str) else res
            finally:
                conn.delete(lock_key)
        else:
            logger.info(f"Gap analysis for {standards_hash} is being calculated by another worker. Waiting...")
            time.sleep(10)


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
