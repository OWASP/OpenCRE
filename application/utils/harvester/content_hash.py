import hashlib


def generate_content_hash(text: str) -> str:
    """
    Generate a deterministic SHA-256 hash for document content.

    Used for artifact-level deduplication.
    """

    return hashlib.sha256(
        text.encode("utf-8"),
    ).hexdigest()
