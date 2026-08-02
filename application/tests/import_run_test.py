"""Tests for import run metadata (Step 6)."""

import json
import unittest
from datetime import datetime, timezone

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

    def test_create_artifact_ingest_event_and_chunk(self) -> None:
        run = db.create_import_run(source="artifact_ingest", version="1.0")
        observed_at = datetime.now(timezone.utc)

        event = db.create_artifact_ingest_event(
            run_id=run.id,
            artifact_id="artifact-1",
            harvest_mode="backfill",
            event_type="discovered",
            source_json={"uri": "https://example.com/source"},
            locator_json={"path": "/tmp/source"},
            artifact_json={"id": "artifact-1"},
            harvest_json={"status": "ok"},
            observed_at=observed_at,
        )

        self.assertIsNotNone(event.id)
        self.assertEqual(event.run_id, run.id)
        self.assertEqual(event.artifact_id, "artifact-1")
        self.assertEqual(
            json.loads(event.source_json), {"uri": "https://example.com/source"}
        )
        self.assertEqual(json.loads(event.locator_json), {"path": "/tmp/source"})
        self.assertEqual(json.loads(event.artifact_json), {"id": "artifact-1"})
        self.assertEqual(json.loads(event.harvest_json), {"status": "ok"})
        self.assertEqual(
            event.observed_at.replace(tzinfo=None),
            observed_at.astimezone(timezone.utc).replace(tzinfo=None),
        )
        self.assertIsNotNone(event.created_at)

        chunk = db.create_ingest_chunk(
            artifact_event_id=event.id,
            chunk_id="chunk-1",
            text="hello world",
            char_count=11,
            span_json={"start": 0, "end": 11},
            delta_json={"op": "add"},
        )

        self.assertIsNotNone(chunk.id)
        self.assertEqual(chunk.artifact_event_id, event.id)
        self.assertEqual(chunk.chunk_id, "chunk-1")
        self.assertEqual(chunk.text, "hello world")
        self.assertEqual(chunk.char_count, 11)
        self.assertEqual(json.loads(chunk.span_json), {"start": 0, "end": 11})
        self.assertEqual(json.loads(chunk.delta_json), {"op": "add"})
        self.assertIsNotNone(chunk.created_at)
