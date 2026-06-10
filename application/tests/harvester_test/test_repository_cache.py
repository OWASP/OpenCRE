from application.utils.harvester.repository_cache import (
    build_repository_cache_path,
)


def test_build_repository_cache_path():
    path = build_repository_cache_path(
        "OWASP",
        "ASVS",
    )

    assert str(path) == ".harvester_cache/owasp/asvs/main"


def test_different_branches_have_different_cache_paths():
    main_path = build_repository_cache_path(
        owner="OWASP",
        repository="ASVS",
        branch="main",
    )

    dev_path = build_repository_cache_path(
        owner="OWASP",
        repository="ASVS",
        branch="dev",
    )

    assert main_path != dev_path
