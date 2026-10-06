"""Tests for SQLAlchemy Postgres URL normalization (psycopg2 dialect)."""

from __future__ import annotations

import unittest

from application.utils.postgres_url import (
    DEFAULT_LOCAL_POSTGRES_URL,
    is_postgres_url,
    sqlalchemy_postgres_url,
)


class TestPostgresUrl(unittest.TestCase):
    def test_detects_postgres_schemes(self) -> None:
        self.assertTrue(is_postgres_url("postgresql://cre:pw@127.0.0.1:5432/cre"))
        self.assertTrue(is_postgres_url("postgres://cre:pw@127.0.0.1:5432/cre"))
        self.assertTrue(
            is_postgres_url("postgresql+psycopg2://cre:pw@127.0.0.1:5432/cre")
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


if __name__ == "__main__":
    unittest.main()
