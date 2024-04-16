import hashlib
from typing import List


def make_subresources_key(standards: List[str], key: str) -> str:
    return str(make_resources_key(standards)) + "->" + key


def make_resources_key(array: List[str]):
    return " >> ".join(array)
