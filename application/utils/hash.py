import hashlib
from typing import List


def make_cache_key(standards: List[str], key: str) -> str:
    return str(make_array_key(standards)) + "->" + key


def make_array_key(array: List[str]):
    return " >> ".join(array)
