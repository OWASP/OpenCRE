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
