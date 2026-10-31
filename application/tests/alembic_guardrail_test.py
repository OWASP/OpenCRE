"""Release guardrail must open Heroku Postgres with the installed driver."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application.config import CMDConfig
from scripts import check_alembic_revision_guardrail as guardrail


class AlembicGuardrailUrlTest(unittest.TestCase):
    def test_heroku_postgres_url_uses_psycopg2(self) -> None:
        heroku_url = "postgres://u:p@host:5432/db"
        with patch.dict(os.environ, {"DATABASE_URL": heroku_url}, clear=True):
            self.assertEqual(
                guardrail._normalized_db_url(),
                "postgresql+psycopg2://u:p@host:5432/db",
            )

    def test_postgresql_url_uses_psycopg2(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://u:p@host:5432/db"},
            clear=True,
        ):
            self.assertEqual(
                guardrail._normalized_db_url(),
                "postgresql+psycopg2://u:p@host:5432/db",
            )

    def test_cli_config_uses_psycopg2(self) -> None:
        cfg = CMDConfig("postgres://u:p@host:5432/db")
        self.assertEqual(
            cfg.SQLALCHEMY_DATABASE_URI,
            "postgresql+psycopg2://u:p@host:5432/db",
        )

    def test_cli_sqlite_path_stays_sqlite(self) -> None:
        cfg = CMDConfig("standards_cache.sqlite")
        self.assertTrue(cfg.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///"))
        self.assertTrue(cfg.SQLALCHEMY_DATABASE_URI.endswith("standards_cache.sqlite"))


if __name__ == "__main__":
    unittest.main()
