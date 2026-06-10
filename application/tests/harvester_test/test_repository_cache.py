from application.utils.harvester.repository_cache import (
    build_repository_cache_path,
)


def test_build_repository_cache_path():
    path = build_repository_cache_path(
        "OWASP",
        "ASVS",
    )

    assert str(path) == ".harvester_cache/owasp/asvs"
