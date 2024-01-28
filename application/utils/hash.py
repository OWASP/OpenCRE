import hashlib
from typing import List


def make_cache_key(standards: List[str], key: str) -> str:
    return make_array_hash(standards) + "->" + key


def make_array_hash(array: List[str]):
    return hashlib.md5(":".join(array).encode("utf-8")).hexdigest()
