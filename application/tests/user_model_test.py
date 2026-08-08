"""Tests for user persistence and per-user resource selection (issue #586, RFC #876 TODO 1/2)."""

import os
import threading
import unittest
from typing import Any, List
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from application import create_app, sqla
from application.database import db


class TestUserModel(unittest.TestCase):
    def setUp(self) -> None:
        # These tests exercise only the SQL layer; skip the Neo4j graph load.
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        os.environ.pop("NO_LOAD_GRAPH_DB", None)

    def test_upsert_user_creates_single_row(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(user.google_sub, "sub-123")
        self.assertEqual(user.email, "a@example.com")
        self.assertEqual(user.display_name, "Alice")
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.last_seen_at)
        self.assertEqual(sqla.session.query(db.User).count(), 1)

    def test_upsert_user_is_idempotent_and_updates_in_place(self) -> None:
        first = self.collection.upsert_user(
            google_sub="sub-123", email="old@example.com", display_name="Alice"
        )
        first_id = first.id
        created_at = first.created_at

        second = self.collection.upsert_user(
            google_sub="sub-123", email="new@example.com", display_name="Alice B"
        )

        # No duplicate row, same identity, refreshed profile fields.
        self.assertEqual(sqla.session.query(db.User).count(), 1)
        self.assertEqual(second.id, first_id)
        self.assertEqual(second.email, "new@example.com")
        self.assertEqual(second.display_name, "Alice B")
        self.assertEqual(second.created_at, created_at)
        self.assertGreaterEqual(second.last_seen_at, created_at)

    def test_upsert_user_tolerates_missing_email_and_name(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-noemail", email="", display_name=None
        )
        self.assertEqual(user.email, "")
        self.assertIsNone(user.display_name)
        self.assertEqual(sqla.session.query(db.User).count(), 1)

    def test_get_user_by_sub(self) -> None:
        self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        found = self.collection.get_user_by_sub("sub-123")
        self.assertIsNotNone(found)
        self.assertEqual(found.google_sub, "sub-123")
        self.assertIsNone(self.collection.get_user_by_sub("does-not-exist"))

    def test_resource_selection_round_trips(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        # Empty by default.
        self.assertEqual(self.collection.get_user_resource_selection(user.id), [])

        stored = self.collection.set_user_resource_selection(
            user.id, ["ASVS", "CWE", "SAMM"]
        )
        self.assertEqual(sorted(stored), ["ASVS", "CWE", "SAMM"])
        self.assertEqual(
            self.collection.get_user_resource_selection(user.id),
            ["ASVS", "CWE", "SAMM"],
        )

    def test_set_resource_selection_replaces_previous(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "CWE"])
        self.collection.set_user_resource_selection(user.id, ["SAMM"])
        self.assertEqual(self.collection.get_user_resource_selection(user.id), ["SAMM"])
        self.assertEqual(
            sqla.session.query(db.UserResourceSelection)
            .filter(db.UserResourceSelection.user_id == user.id)
            .count(),
            1,
        )

    def test_set_resource_selection_dedupes_input(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "ASVS", "CWE"])
        self.assertEqual(
            self.collection.get_user_resource_selection(user.id), ["ASVS", "CWE"]
        )

    def test_resource_selection_is_per_user(self) -> None:
        alice = self.collection.upsert_user(
            google_sub="sub-a", email="a@example.com", display_name="Alice"
        )
        bob = self.collection.upsert_user(
            google_sub="sub-b", email="b@example.com", display_name="Bob"
        )
        self.collection.set_user_resource_selection(alice.id, ["ASVS"])
        self.collection.set_user_resource_selection(bob.id, ["CWE"])
        self.assertEqual(
            self.collection.get_user_resource_selection(alice.id), ["ASVS"]
        )
        self.assertEqual(self.collection.get_user_resource_selection(bob.id), ["CWE"])

    def test_resource_selection_unique_constraint_enforced(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        from datetime import datetime, timezone

        sqla.session.add(
            db.UserResourceSelection(
                user_id=user.id,
                standard_name="ASVS",
                created_at=datetime.now(timezone.utc),
            )
        )
        sqla.session.add(
            db.UserResourceSelection(
                user_id=user.id,
                standard_name="ASVS",
                created_at=datetime.now(timezone.utc),
            )
        )
        with self.assertRaises(IntegrityError):
            sqla.session.commit()
        sqla.session.rollback()

    def test_deleting_user_cascades_to_selection(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-123", email="a@example.com", display_name="Alice"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "CWE"])
        sqla.session.delete(user)
        sqla.session.commit()
        self.assertEqual(sqla.session.query(db.UserResourceSelection).count(), 0)

    def test_set_resource_selection_recovers_from_integrity_error(self) -> None:
        # A concurrent PUT can make the first commit raise IntegrityError on
        # uq_user_resource_selection. The method must roll back and retry once,
        # then return the correct selection.
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        real_commit = self.collection.session.commit
        calls = {"n": 0}

        def flaky_commit(*args: Any, **kwargs: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError(
                    "stmt", {}, Exception("uq_user_resource_selection")
                )
            real_commit()

        with patch.object(self.collection.session, "commit", side_effect=flaky_commit):
            result = self.collection.set_user_resource_selection(
                user.id, ["ASVS", "CWE"]
            )

        self.assertEqual(sorted(result), ["ASVS", "CWE"])
        self.assertEqual(calls["n"], 2)  # retried exactly once

    def test_set_resource_selection_reraises_on_persistent_integrity_error(
        self,
    ) -> None:
        # If the retry also fails, the error propagates — the recovery must not
        # loop indefinitely (retry exactly once).
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )

        def always_raise(*args: Any, **kwargs: Any) -> None:
            raise IntegrityError("stmt", {}, Exception("uq_user_resource_selection"))

        with patch.object(self.collection.session, "commit", side_effect=always_raise):
            with self.assertRaises(IntegrityError):
                self.collection.set_user_resource_selection(user.id, ["ASVS"])
        self.collection.session.rollback()

    def test_set_resource_selection_blocks_on_locked_user_row(self) -> None:
        # The replacement serializes per user by locking the User row: a second
        # writer must WAIT for the first to commit (so its DELETE then sees the
        # first's rows, instead of the two selections merging). Reproduced
        # deterministically: hold the user-row lock here, then assert a worker's
        # set_user_resource_selection blocks until we release it. Postgres-only —
        # FOR UPDATE is a no-op on SQLite, so nothing would block there.
        if "postgresql" not in str(sqla.engine.url):
            self.skipTest("row-lock serialization requires Postgres (FOR UPDATE)")

        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        user_id = user.id
        self.collection.set_user_resource_selection(user_id, ["ASVS"])  # seed
        self.collection.session.rollback()

        # Acquire and HOLD the user-row lock on this session (open transaction).
        self.collection.session.query(db.User).filter(
            db.User.id == user_id
        ).with_for_update().first()

        done = threading.Event()
        errors: List[Exception] = []

        def worker() -> None:
            with self.app.app_context():
                try:
                    # Empty replacement = DELETE only, no INSERT. So the only
                    # thing that can make this touch (and block on) the User row
                    # is the method's own FOR UPDATE — which isolates it from the
                    # FK lock an INSERT would otherwise take.
                    db.Node_collection().set_user_resource_selection(user_id, [])
                except Exception as e:
                    errors.append(e)
                finally:
                    sqla.session.remove()
                    done.set()

        t = threading.Thread(target=worker)
        t.start()

        # While we hold the lock the worker must block — it cannot finish.
        self.assertFalse(
            done.wait(timeout=2), "worker did not block on the user-row lock"
        )

        # Release the lock; the worker now proceeds and completes.
        self.collection.session.rollback()
        self.assertTrue(
            done.wait(timeout=15), "worker did not finish after lock release"
        )
        t.join(timeout=5)

        self.assertEqual(errors, [])
        self.collection.session.rollback()  # fresh snapshot
        self.assertEqual(self.collection.get_user_resource_selection(user_id), [])


if __name__ == "__main__":
    unittest.main()
