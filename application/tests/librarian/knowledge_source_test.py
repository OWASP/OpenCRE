"""Tests for the two knowledge sources (C's read side).

``DbKnowledgeSource`` runs against an in-memory SQLite DB
(``create_app(mode="test")`` + ``create_all``), matching the project's
``db_test.py`` pattern — no migration needed.

The behaviour that matters here is what the source *refuses* to read: consumed
rows, other runs' rows, and ``NOISE`` — the label B's recall-first guarantee
turns on. ``UNCERTAIN`` is read and decided like any other label; it used to be
skipped and left to Module D, which stranded those rows.

The lock tests cover the other half: that the default read takes no row lock
(one consumer, per the contract) and that asking for one on a dialect that
cannot honour it fails loudly instead of handing back an unlocked batch.
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

    def test_reads_both_of_bs_labels(self) -> None:
        """B is recall-first: it drops NOISE and forwards KNOWLEDGE *and*
        UNCERTAIN. An UNCERTAIN chunk is one B was unsure about classifying, not
        one it judged worthless, so C reads it too — leaving it stranded meant
        nothing ever retrieved candidates for it."""
        sqla.session.add_all([_row("a"), _row("b", llm_label="UNCERTAIN")])
        sqla.session.commit()

        items = list(DbKnowledgeSource(sqla.session).items())

        self.assertEqual(sorted(i.id for i in items), ["a", "b"])
        self.assertEqual(sorted(i.llm_label for i in items), ["KNOWLEDGE", "UNCERTAIN"])

    def test_noise_is_never_read(self) -> None:
        """B drops NOISE before the queue, but if one ever appeared C must not
        treat it as work — the label is what B's recall-first guarantee turns on."""
        sqla.session.add_all([_row("a"), _row("n", llm_label="NOISE")])
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

    def test_default_read_takes_no_row_lock(self) -> None:
        """One consumer is the contract, so the default read must not pay for a
        lock — and must not fail on SQLite, which cannot grant one."""
        sqla.session.add_all([_row("a")])
        sqla.session.commit()

        sql = _as_postgres_sql(DbKnowledgeSource(sqla.session)._query())

        self.assertNotIn("FOR UPDATE", sql)

    def test_lock_rows_is_refused_when_the_dialect_cannot_honour_it(self) -> None:
        """Silently dropping the clause would hand an unlocked batch to a caller
        who asked for a locked one; the duplicated work would surface under load,
        nowhere near this code. So SQLite refuses instead."""
        sqla.session.add_all([_row("a")])
        sqla.session.commit()

        source = DbKnowledgeSource(sqla.session, lock_rows=True)
        with self.assertRaises(ValueError) as caught:
            list(source.items())

        self.assertIn("sqlite", str(caught.exception))

    def test_lock_rows_emits_skip_locked_on_postgres(self) -> None:
        """The clause itself, checked against a fake bind — the real thing needs a
        Postgres server, and Module C has not been run against one yet."""
        sqla.session.add_all([_row("a")])
        sqla.session.commit()

        source = DbKnowledgeSource(sqla.session, lock_rows=True)
        # Only the dialect decision is faked; the query itself is the real one.
        source._session = _PostgresLookalike(sqla.session)
        sql = _as_postgres_sql(source._query())

        self.assertIn("FOR UPDATE", sql)
        self.assertIn("SKIP LOCKED", sql)


_PG_URL_ENV = "LIBRARIAN_POSTGRES_TEST_URL"


@unittest.skipUnless(
    os.environ.get(_PG_URL_ENV),
    f"set {_PG_URL_ENV} to a Postgres URL to run the real locking test",
)
class DbKnowledgeSourceLockingPostgresTest(unittest.TestCase):
    """Two live consumers over one queue — the only test that proves the claim.

    Everything else about ``lock_rows`` is asserted against generated SQL, which
    shows the clause is *emitted*, not that Postgres hands two consumers disjoint
    rows. That needs a real server and two concurrent transactions, so it lives
    behind an env var rather than in the default (SQLite, single-consumer) run:

        LIBRARIAN_POSTGRES_TEST_URL=postgresql://user:pw@localhost/opencre_test \
            python -m pytest application/tests/librarian/knowledge_source_test.py -k Postgres

    Asked for by CodeRabbit on #1030. Until it has actually been run, the runbook
    lists concurrent consumers as unverified.
    """

    def setUp(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        self.engine = create_engine(os.environ[_PG_URL_ENV])
        KnowledgeQueueRow.__table__.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)
        seed = self.Session()
        seed.query(KnowledgeQueueRow).delete()
        seed.add_all([_row("a"), _row("b"), _row("c"), _row("d")])
        seed.commit()
        seed.close()

    def tearDown(self) -> None:
        wipe = self.Session()
        wipe.query(KnowledgeQueueRow).delete()
        wipe.commit()
        wipe.close()
        self.engine.dispose()

    def test_two_consumers_claim_disjoint_rows_and_release_on_rollback(self) -> None:
        first, second = self.Session(), self.Session()
        try:
            # First consumer claims two rows and holds the transaction open.
            claimed_first = [
                i.id for i in DbKnowledgeSource(first, limit=2, lock_rows=True).items()
            ]
            self.assertEqual(len(claimed_first), 2)

            # Second consumer, concurrently: SKIP LOCKED must step over the held
            # rows rather than block on them or hand back the same ones.
            claimed_second = [
                i.id for i in DbKnowledgeSource(second, limit=2, lock_rows=True).items()
            ]
            self.assertEqual(
                set(claimed_first) & set(claimed_second),
                set(),
                "concurrent consumers must claim disjoint rows",
            )
            self.assertEqual(len(claimed_second), 2)

            # Ending the first transaction releases its claim.
            first.rollback()
            third = self.Session()
            try:
                after = [
                    i.id
                    for i in DbKnowledgeSource(third, limit=4, lock_rows=True).items()
                ]
                self.assertEqual(
                    set(claimed_first) - set(after),
                    set(),
                    "rolled-back locks must be claimable again",
                )
            finally:
                third.rollback()
                third.close()
        finally:
            for s in (first, second):
                s.rollback()
                s.close()


def _as_postgres_sql(query: object) -> str:
    """Render a Query as Postgres would.

    Not a detail to skip: SQLAlchemy's SQLite compiler emits an empty
    ``for_update_clause``, so compiling against the test bind hides the very
    clause these tests exist to check, and both assertions would pass no matter
    what ``_locked`` did.
    """
    from sqlalchemy.dialects import postgresql

    return str(query.statement.compile(dialect=postgresql.dialect())).upper()


class _PostgresLookalike:
    """A session that answers "postgresql" but delegates everything else.

    ``connection_dialect_name`` reads the bind, so claiming the dialect is all it
    takes to exercise the branch without a Postgres server.
    """

    def __init__(self, session: object) -> None:
        self._session = session
        self.dialect = type("_Dialect", (), {"name": "postgresql"})()

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)


if __name__ == "__main__":
    unittest.main()
