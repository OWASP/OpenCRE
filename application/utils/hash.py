import hashlib

def make_array_hash(array: list):
    return hashlib.md5(":".join(array).encode("utf-8")).hexdigest()

