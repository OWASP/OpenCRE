def generate_artifact_id(repository: str, file_path: str) -> str:
    """
    Generate a stable artifact identifier for a repository file.

    Example:
        repository = "OWASP/ASVS"
        file_path = "5.0/en/0x01-Frontispiece.md"

        -> art:OWASP/ASVS:5.0/en/0x01-Frontispiece.md
    """
    return f"art:{repository}:{file_path}"
