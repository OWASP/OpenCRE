import hashlib


def make_cache_key(standards: list, key: str) -> str:
    return make_array_hash(standards) + "->" + key


def make_array_hash(array: list):
    return hashlib.md5(":".join(array).encode("utf-8")).hexdigest()
