import importlib.util
import sys
import unittest
from pathlib import Path

from application.utils.db_url import (
    assert_local_clone_url,
    assert_local_db_url,
    redact_db_url,
)

_REMOTE_URLS = (
    "postgresql://cre:pw@100.74.143.62:5432/cre_prodclone",
    "postgresql://cre:pw@db.example.com:5432/cre_prodclone",
    "postgres://u:p@ec2-1-2-3-4.compute-1.amazonaws.com:5432/dxyz",
    "postgresql://cre:pw@127.0.0.1:5432/opencreorg",
    "postgresql://cre:pw@heroku-host.example/cre_prodclone",
)
_LOCAL_URLS = (
    "postgresql://cre:password@127.0.0.1:5432/cre_prodclone",
    "postgresql://cre:password@localhost:5432/cre_grid_w0",
    "sqlite:///tmp/x.sqlite",
    "standards_cache.sqlite",
)


class AssertLocalDbUrlTest(unittest.TestCase):
    def test_refuses_remote_heroku_and_production_urls(self) -> None:
        for url in _REMOTE_URLS:
            with self.subTest(url=url), self.assertRaises(SystemExit):
                assert_local_db_url(url)

    def test_refuses_empty_url(self) -> None:
        for url in ("", "   "):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                assert_local_db_url(url)

    def test_allows_local_urls_including_database_cre(self) -> None:
        for url in _LOCAL_URLS + ("postgresql://cre:password@127.0.0.1:5432/cre",):
            with self.subTest(url=url):
                assert_local_db_url(url)


class AssertLocalCloneUrlTest(unittest.TestCase):
    def test_refuses_everything_the_local_check_refuses(self) -> None:
        for url in _REMOTE_URLS + ("",):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                assert_local_clone_url(url)

    def test_refuses_database_named_cre(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            assert_local_clone_url("postgresql://cre:password@127.0.0.1:5432/cre")
        self.assertIn("cre_prodclone", str(ctx.exception))

    def test_allows_local_clones(self) -> None:
        for url in _LOCAL_URLS:
            with self.subTest(url=url):
                assert_local_clone_url(url)


class RedactDbUrlTest(unittest.TestCase):
    def test_masks_password_and_keeps_rest(self) -> None:
        self.assertEqual(
            redact_db_url("postgresql://cre:s3cret@127.0.0.1:5432/cre?sslmode=require"),
            "postgresql://cre:***@127.0.0.1:5432/cre?sslmode=require",
        )

    def test_url_without_password_is_unchanged(self) -> None:
        for url in (
            "postgresql://127.0.0.1/cre",
            "postgresql://cre@127.0.0.1/cre",
            "sqlite:///tmp/x.sqlite",
            "standards_cache.sqlite",
            "",
        ):
            self.assertEqual(redact_db_url(url), url)

    def test_password_with_special_characters(self) -> None:
        self.assertEqual(
            redact_db_url("postgres://u:p%40ss:word@db.example.com/x"),
            "postgres://u:***@db.example.com/x",
        )


def _load_script(relative_path: str, name: str):  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


class EvalScriptsRefuseUnsafeDatabasesTest(unittest.TestCase):
    """Eval scripts empty the OIE queue tables, so they must refuse a remote
    database before touching it. The URLs below use the reserved .invalid TLD, so
    nothing can connect even if a guard is missing. Never point these tests at a
    local database: without the guard the script would clear its queue tables.
    The `cre`-database rule is covered by AssertLocalCloneUrlTest."""

    def test_run_full_pipeline_refuses_remote_host(self) -> None:
        module = _load_script(
            "scripts/oie_owasp_eval/run_full_pipeline.py", "run_full_pipeline_guard"
        )
        with self.assertRaises(SystemExit):
            module.main(["--cache_file", "postgresql://cre:pw@db.invalid:5432/x"])

    def test_run_b2_pr_mappings_refuses_remote_host(self) -> None:
        module = _load_script(
            "scripts/oie_owasp_eval/run_b2_pr_mappings.py", "run_b2_guard"
        )
        with self.assertRaises(SystemExit):
            module.run_pipeline(
                "rid", "postgresql://cre:pw@db.invalid:5432/x", keep_all_knowledge=False
            )


if __name__ == "__main__":
    unittest.main()
