"""Tests for import run metadata (Step 6)."""

import unittest
from application import create_app, sqla
from application.database import db


class TestImportRun(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def test_create_import_run(self) -> None:
        run = db.create_import_run(source="test_source", version="1.0")
        self.assertIsNotNone(run.id)
        self.assertEqual(run.source, "test_source")
        self.assertEqual(run.version, "1.0")
        self.assertIsNotNone(run.created_at)

    def test_get_latest_import_run(self) -> None:
        db.create_import_run(source="test_source", version="1.0")
        run2 = db.create_import_run(source="test_source", version="2.0")
        latest = db.get_latest_import_run("test_source")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, run2.id)
        self.assertEqual(latest.version, "2.0")
