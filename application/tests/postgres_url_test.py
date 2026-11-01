"""Unit tests for application.utils.postgres_url."""

from __future__ import annotations

import unittest

from application.utils.postgres_url import (
    is_postgres_url,
    main_db_env_keys,
    sqlalchemy_postgres_url,
)


class TestPostgresUrl(unittest.TestCase):
    def test_is_postgres_url(self) -> None:
        self.assertTrue(is_postgres_url("postgresql://cre:pw@host/db"))
        self.assertTrue(is_postgres_url("postgres://cre:pw@host/db"))
        self.assertFalse(is_postgres_url("sqlite:////tmp/x.db"))

    def test_sqlalchemy_pins_psycopg2(self) -> None:
        self.assertEqual(
            sqlalchemy_postgres_url("postgresql://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )
        self.assertEqual(
            sqlalchemy_postgres_url("postgres://cre:pw@host/db"),
            "postgresql+psycopg2://cre:pw@host/db",
        )

    def test_main_db_env_keys_order(self) -> None:
        self.assertEqual(
            main_db_env_keys("development")[0],
            "DEV_DATABASE_URL",
        )
        self.assertEqual(
            main_db_env_keys("production")[0],
            "DATABASE_URL",
        )


if __name__ == "__main__":
    unittest.main()
