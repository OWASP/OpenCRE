import requests
import time

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
                if res1.json():
                    if res1.json().get("result"):
                        waiting.remove(f"{sa}->{sb}")
                res2 = requests.get(
                    f"{target_url}/rest/v1/map_analysis?standard={sb}&standard={sa}"
                )
                if res2.json():
                    if res2.json().get("result"):
                        waiting.remove(f"{sb}->{sa}")
        print(f"calculating {len(waiting)} gap analyses")
        print(waiting)
        time.sleep(30)
    print("map analysis preloaded successfully")
