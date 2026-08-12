"""Tests for the two knowledge sources (C's read side).

``DbKnowledgeSource`` runs against an in-memory SQLite DB
(``create_app(mode="test")`` + ``create_all``), matching the project's
``db_test.py`` pattern — no migration needed.

The behaviour that matters here is what the source *refuses* to read: consumed
rows, other runs' rows, and — the one with a cross-module consequence —
``UNCERTAIN`` rows, which belong to Module D.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database.db import KnowledgeQueueItem as KnowledgeQueueRow
from application.utils.librarian.knowledge_source import (
    DbKnowledgeSource,
    FixtureKnowledgeSource,
)

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_knowledge_queue.jsonl"
)


def _row(row_id: str, **overrides) -> KnowledgeQueueRow:
    values = dict(
        id=row_id,
        content_hash=f"hash-{row_id}",
        chunk_id=f"chk:art:OWASP/ASVS:a.md:{row_id}",
        artifact_id="art:OWASP/ASVS:a.md",
        pipeline_run_id="run-1",
        schema_version="0.2.0",
        source_type="github",
        source_repo="OWASP/ASVS",
        source_commit_sha="abc1234567890",
        source_committed_at="2026-05-24T18:02:11Z",
        locator_kind="repo_path",
        locator_path="a.md",
        span_index=0,
        span_total=1,
        text="Verify that passwords are at least 12 characters.",
        llm_label="KNOWLEDGE",
        confidence=0.9,
        created_at=datetime(2026, 5, 25, 2, 25, 0, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return KnowledgeQueueRow(**values)


class FixtureKnowledgeSourceTest(unittest.TestCase):
    def test_reads_the_bundled_v0_2_fixture(self) -> None:
        rows = list(FixtureKnowledgeSource(_FIXTURE).items())
        self.assertEqual(len(rows), 5)
        # The fixture carries both source shapes B writes.
        self.assertEqual({r.source_type.value for r in rows}, {"github", "rss"})

    def test_malformed_line_is_skipped_not_fatal(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(json.dumps({"id": "nope"}) + "\n")
            with open(_FIXTURE, encoding="utf-8") as src:
                fh.write(src.readline())
            tmp = fh.name
        try:
            with self.assertLogs(
                "application.utils.librarian.knowledge_source", level="WARNING"
            ):
                rows = list(FixtureKnowledgeSource(tmp).items())
            self.assertEqual(len(rows), 1)
        finally:
            os.unlink(tmp)


class DbKnowledgeSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_reads_unconsumed_knowledge_rows(self) -> None:
        sqla.session.add_all([_row("a"), _row("b")])
        sqla.session.commit()

        items = list(DbKnowledgeSource(sqla.session).items())

        self.assertEqual([i.id for i in items], ["a", "b"])
        # The SQLAlchemy row validates straight into C's mirror.
        self.assertEqual(items[0].chunk_id, "chk:art:OWASP/ASVS:a.md:a")

    def test_consumed_rows_are_not_re_read(self) -> None:
        sqla.session.add_all(
            [
                _row("a"),
                _row("b", consumed_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            ]
        )
        sqla.session.commit()

        items = list(DbKnowledgeSource(sqla.session).items())

        self.assertEqual([i.id for i in items], ["a"])

    def test_uncertain_rows_are_left_for_module_d(self) -> None:
        """B writes UNCERTAIN for Module D's human review. If C read those rows
        it would also mark them consumed, silently emptying D's queue."""
        sqla.session.add_all([_row("a"), _row("b", llm_label="UNCERTAIN")])
        sqla.session.commit()

        items = list(DbKnowledgeSource(sqla.session).items())

        self.assertEqual([i.id for i in items], ["a"])

    def test_scopes_to_one_pipeline_run(self) -> None:
        sqla.session.add_all([_row("a"), _row("b", pipeline_run_id="run-2")])
        sqla.session.commit()

        items = list(DbKnowledgeSource(sqla.session, pipeline_run_id="run-2").items())

        self.assertEqual([i.id for i in items], ["b"])

    def test_limit_is_applied_in_a_stable_order(self) -> None:
        """created_at alone is not unique — B inserts a batch in one
        transaction — so the id break is what makes a limited run repeatable."""
        sqla.session.add_all([_row("c"), _row("a"), _row("b")])
        sqla.session.commit()

        first = [i.id for i in DbKnowledgeSource(sqla.session, limit=2).items()]
        again = [i.id for i in DbKnowledgeSource(sqla.session, limit=2).items()]

        self.assertEqual(first, ["a", "b"])
        self.assertEqual(first, again)

    def test_unmodellable_row_is_skipped_not_fatal(self) -> None:
        """A row B wrote that C cannot model must not abort the batch."""
        sqla.session.add_all([_row("a"), _row("b", source_type="carrier-pigeon")])
        sqla.session.commit()

        with self.assertLogs(
            "application.utils.librarian.knowledge_source", level="WARNING"
        ):
            items = list(DbKnowledgeSource(sqla.session).items())

        self.assertEqual([i.id for i in items], ["a"])


if __name__ == "__main__":
    unittest.main()
