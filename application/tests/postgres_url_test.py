"""Tests for SQLAlchemy Postgres URL normalization (psycopg2 dialect)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application.config import CMDConfig, _sqlalchemy_uri_from_env
from application.utils.db_backend import detect_backend
from application.utils.owasp_agent.index_store import app_db_url_and_key
from application.utils.postgres_url import (
    DEFAULT_LOCAL_POSTGRES_URL,
    is_postgres_url,
    main_db_env_keys,
    sqlalchemy_postgres_url,
)


class TestPostgresUrl(unittest.TestCase):
    def test_detects_postgres_schemes(self) -> None:
        self.assertTrue(is_postgres_url("postgresql://cre:pw@127.0.0.1:5432/cre"))
        self.assertTrue(is_postgres_url("postgres://cre:pw@127.0.0.1:5432/cre"))
        self.assertTrue(
            is_postgres_url("postgresql+psycopg2://cre:pw@127.0.0.1:5432/cre")
        )
        self.assertTrue(
            is_postgres_url("postgresql+psycopg://cre:pw@127.0.0.1:5432/cre")
        )
        self.assertFalse(is_postgres_url("sqlite://"))
        self.assertFalse(is_postgres_url(""))

    def test_rewrites_to_psycopg2_dialect(self) -> None:
        self.assertEqual(
            sqlalchemy_postgres_url("postgresql://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )
        self.assertEqual(
            sqlalchemy_postgres_url("postgres://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )
        self.assertEqual(
            sqlalchemy_postgres_url("postgresql+psycopg2://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )
        self.assertEqual(
            sqlalchemy_postgres_url("postgresql+psycopg://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )

    def test_rejects_sqlite(self) -> None:
        with self.assertRaises(ValueError):
            sqlalchemy_postgres_url("sqlite://")
        with self.assertRaises(ValueError):
            sqlalchemy_postgres_url("sqlite:////tmp/x.sqlite")

    def test_default_local_url_is_docker_make_target(self) -> None:
        self.assertEqual(
            DEFAULT_LOCAL_POSTGRES_URL,
            "postgresql://cre:password@127.0.0.1:5432/cre",
        )

    def test_main_db_env_keys_match_flask_and_agent(self) -> None:
        self.assertEqual(
            main_db_env_keys("production"),
            ("DATABASE_URL", "PROD_DATABASE_URL", "SQLALCHEMY_DATABASE_URI"),
        )
        self.assertEqual(
            main_db_env_keys("development"),
            ("DEV_DATABASE_URL", "DATABASE_URL", "SQLALCHEMY_DATABASE_URI"),
        )

    def test_production_prefers_database_url_over_prod_alias(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "DATABASE_URL",
                "PROD_DATABASE_URL",
                "DEV_DATABASE_URL",
                "SQLALCHEMY_DATABASE_URI",
                "FLASK_CONFIG",
            }
        }
        env["FLASK_CONFIG"] = "production"
        env["DATABASE_URL"] = "postgresql://heroku/db"
        env["PROD_DATABASE_URL"] = "postgresql://prod-only/db"
        with patch.dict(os.environ, env, clear=True):
            url, key = app_db_url_and_key()
            self.assertEqual(key, "DATABASE_URL")
            self.assertEqual(url, "postgresql://heroku/db")
            # Same precedence Flask ProductionConfig uses via main_db_env_keys.
            first = next(
                (
                    os.environ[k]
                    for k in main_db_env_keys("production")
                    if os.environ.get(k)
                ),
                "",
            )
            self.assertEqual(first, "postgresql://heroku/db")

    def test_sqlalchemy_uri_from_env_and_cmdconfig(self) -> None:
        self.assertEqual(
            _sqlalchemy_uri_from_env("postgresql://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )
        self.assertTrue(_sqlalchemy_uri_from_env("sqlite:///x").startswith("sqlite:"))
        cmd = CMDConfig("postgres://cre:pw@host/db")
        self.assertEqual(
            cmd.SQLALCHEMY_DATABASE_URI, "postgresql+psycopg2://cre:pw@host/db"
        )

    def test_detect_backend_uses_shared_helper(self) -> None:
        self.assertTrue(detect_backend("postgresql+psycopg://x/y").is_postgres)
        self.assertTrue(detect_backend("postgresql+psycopg2://x/y").is_postgres)
        self.assertFalse(detect_backend("sqlite://").is_postgres)


if __name__ == "__main__":
    unittest.main()
