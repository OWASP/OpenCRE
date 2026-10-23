"""Tests for the MyOpenCRE mapping job (#965, RFC TODO 2 + 3).

Hermetic and fixture-driven, as the RFC asks: an in-memory graph with a few
CREs, one user with one standard and its sections, and stub Librarian
components with fixed confidences. What is proved is the contract, not the
model: deterministic status counts, the stored ``cre_db_id`` is a validated
internal id, user decisions are never rewritten, and a re-run is a no-op.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database import db
from application.database.db import SectionStatus, User
from application.defs import cre_defs as defs
from application.utils.librarian.config_loader import LibrarianConfig
from application.utils.librarian.factory import LibrarianComponents
from application.utils.librarian.schemas import CreCandidate, RetrievalAudit
from application.utils.mapping_job import (
    DEFAULT_QUEUE,
    REMAP_AFTER_REINDEX,
    MappingPartialFailure,
    MappingSummary,
    check_complete,
    run_mapping,
)

AT = datetime(2026, 10, 24, tzinfo=timezone.utc).replace(tzinfo=None)


def _config(threshold: float = 0.80) -> LibrarianConfig:
    return LibrarianConfig(
        crossencoder_model="stub",
        retriever_backend="in_memory",
        top_k_retrieval=20,
        top_k_rerank=5,
        link_threshold=threshold,
        temperature=1.0,
        batch_size=32,
        ece_target=0.10,
        conformal_alpha=0.10,
    )


class _Retriever:
    """text -> candidate ids; a text with no entry retrieves nothing."""

    def __init__(self, by_text):
        self.by_text = by_text

    def retrieve(self, text):
        ids = self.by_text.get(text, [])
        if ids == "boom":
            raise RuntimeError("embedding timeout")
        return RetrievalAudit(
            retriever="stub/1.0.0",
            candidates=[CreCandidate(cre_id=i, score_vector=0.9) for i in ids],
            reranked=[],
            threshold=0.0,
        )


class _Reranker:
    def rerank(self, text, audit):
        return audit.model_copy(
            update={
                "reranked": [
                    CreCandidate(cre_id=c.cre_id, score_rerank=10.0)
                    for c in audit.candidates
                ]
            }
        )


class _Scaler:
    """Confidence keyed by the first logit's position: tests set one value
    per section through the retriever's candidate id instead."""

    def __init__(self, by_cre):
        self.by_cre = by_cre
        self.current = None

    def confidence(self, logits):
        return self.by_cre.get(self.current, 0.0)


def _components(by_text, conf_by_cre):
    retriever = _Retriever(by_text)
    scaler = _Scaler(conf_by_cre)

    class _Tracking(_Retriever):
        def retrieve(self, text):
            audit = super().retrieve(text)
            scaler.current = audit.candidates[0].cre_id if audit.candidates else None
            return audit

    return LibrarianComponents(
        retriever=_Tracking(by_text),
        reranker=_Reranker(),
        scaler=scaler,
        known_cre_ids=frozenset(conf_by_cre),
    )


class MappingJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.user = User(
            google_sub="sub-1", email="u@example.org", created_at=AT, last_seen_at=AT
        )
        self.other = User(
            google_sub="sub-2", email="o@example.org", created_at=AT, last_seen_at=AT
        )
        sqla.session.add_all([self.user, self.other])
        sqla.session.commit()
        self.nonce = self.collection.add_cre(
            defs.CRE(
                id="287-251", name="Use a unique challenge nonce", tags=["Cryptography"]
            )
        )
        self.salt = self.collection.add_cre(
            defs.CRE(id="082-530", name="Unique random salt")
        )
        self.standard = self.collection.create_user_standard(self.user.id, "My Policy")
        self.collection.upsert_user_standard_sections(
            self.standard.id,
            [
                ("1.1", "challenge nonce must be 64 bits"),
                ("1.2", "salt every credential"),
                ("1.3", "sessions expire after logout"),
                ("1.4", "something no CRE covers"),
            ],
        )
        # retrieval is keyed by the graph's INTERNAL ids, as in production
        self.by_text = {
            "challenge nonce must be 64 bits": [self.nonce.id],
            "salt every credential": [self.salt.id],
            "sessions expire after logout": [self.nonce.id],
            "something no CRE covers": [],
        }
        self.conf = {self.nonce.id: 0.95, self.salt.id: 0.42}

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _rows(self):
        return {
            r.section_id: r
            for r in self.collection.get_user_standard_sections(
                self.standard.id, self.user.id
            )
        }

    def test_upload_starts_every_section_pending(self) -> None:
        self.assertEqual({r.status for r in self._rows().values()}, {"PENDING"})

    def test_deterministic_status_counts(self) -> None:
        summary = run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(),
        )

        self.assertEqual(
            (
                summary.considered,
                summary.auto_mapped,
                summary.needs_review,
                summary.unmappable,
                summary.errored,
            ),
            (4, 2, 1, 1, 0),
        )
        rows = self._rows()
        self.assertEqual(rows["1.1"].status, SectionStatus.AUTO_MAPPED.value)
        self.assertEqual(rows["1.3"].status, SectionStatus.AUTO_MAPPED.value)
        self.assertEqual(rows["1.2"].status, SectionStatus.NEEDS_REVIEW.value)
        self.assertEqual(rows["1.4"].status, SectionStatus.UNMAPPABLE.value)

    def test_stored_cre_db_id_is_the_validated_internal_id(self) -> None:
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(),
        )
        rows = self._rows()
        self.assertEqual(rows["1.1"].cre_db_id, self.nonce.id)
        self.assertEqual(rows["1.1"].confidence, 0.95)
        # a review row keeps the candidate as the reviewer's hint
        self.assertEqual(rows["1.2"].cre_db_id, self.salt.id)
        self.assertEqual(rows["1.2"].confidence, 0.42)
        self.assertIsNone(rows["1.4"].cre_db_id)
        self.assertIsNone(rows["1.4"].confidence)

    def test_candidate_the_graph_cannot_resolve_goes_to_review_without_a_reference(
        self,
    ) -> None:
        by_text = dict(
            self.by_text, **{"challenge nonce must be 64 bits": ["ghost-id"]}
        )
        conf = dict(self.conf, **{"ghost-id": 0.99})
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(by_text, conf),
            config=_config(),
        )
        row = self._rows()["1.1"]
        self.assertEqual(row.status, SectionStatus.NEEDS_REVIEW.value)
        self.assertIsNone(row.cre_db_id)

    def test_rerun_is_a_no_op(self) -> None:
        comps = _components(self.by_text, self.conf)
        run_mapping(
            self.standard.id, self.collection, components=comps, config=_config()
        )
        again = run_mapping(
            self.standard.id, self.collection, components=comps, config=_config()
        )
        self.assertEqual(again.considered, 0)

    def test_user_confirmed_rows_are_never_remapped(self) -> None:
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(),
        )
        row = self._rows()["1.2"]
        self.assertTrue(
            self.collection.confirm_section_mapping(row.id, self.nonce.id, self.user.id)
        )
        # a re-index re-run over every mappable status must leave it alone
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(
                self.by_text, {self.nonce.id: 0.1, self.salt.id: 0.1}
            ),
            config=_config(),
            statuses=REMAP_AFTER_REINDEX,
        )
        row = self._rows()["1.2"]
        self.assertEqual(row.status, SectionStatus.USER_CONFIRMED.value)
        self.assertEqual(row.cre_db_id, self.nonce.id)
        # ...while the undecided rows were re-mapped under the new confidences
        self.assertEqual(self._rows()["1.1"].status, SectionStatus.NEEDS_REVIEW.value)

    def test_errored_section_stays_pending_and_is_counted(self) -> None:
        by_text = dict(self.by_text, **{"salt every credential": "boom"})
        summary = run_mapping(
            self.standard.id,
            self.collection,
            components=_components(by_text, self.conf),
            config=_config(),
        )
        self.assertEqual(summary.errored, 1)
        self.assertEqual(self._rows()["1.2"].status, SectionStatus.PENDING.value)

    def test_threshold_comes_from_the_librarian_config(self) -> None:
        summary = run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(threshold=0.40),
        )
        self.assertEqual(summary.auto_mapped, 3)
        self.assertEqual(summary.needs_review, 0)

    def test_confirm_rejects_a_cre_not_in_the_graph(self) -> None:
        row = self._rows()["1.1"]
        self.assertFalse(
            self.collection.confirm_section_mapping(row.id, "nope", self.user.id)
        )

    def test_another_user_sees_nothing_and_cannot_decide(self) -> None:
        self.assertEqual(
            self.collection.get_user_standard_sections(self.standard.id, self.other.id),
            [],
        )
        row = self._rows()["1.1"]
        self.assertFalse(self.collection.reject_section_mapping(row.id, self.other.id))

    def test_reupload_resets_changed_text_but_keeps_user_decisions(self) -> None:
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(),
        )
        rows = self._rows()
        self.collection.confirm_section_mapping(
            rows["1.1"].id, self.nonce.id, self.user.id
        )
        touched = self.collection.upsert_user_standard_sections(
            self.standard.id,
            [
                ("1.1", "changed text"),
                ("1.2", "changed text too"),
                ("1.3", "sessions expire after logout"),
            ],
        )
        self.assertEqual(touched, 2)
        rows = self._rows()
        self.assertEqual(rows["1.1"].status, SectionStatus.USER_CONFIRMED.value)
        self.assertEqual(rows["1.2"].status, SectionStatus.PENDING.value)
        self.assertIsNone(rows["1.2"].cre_db_id)
        self.assertEqual(rows["1.3"].status, SectionStatus.AUTO_MAPPED.value)

    def test_duplicate_section_ids_in_one_upload_last_one_wins(self) -> None:
        """A repeated section id must update the row added moments earlier in
        the same call, not insert a second one into the unique constraint."""
        std = self.collection.create_user_standard(self.user.id, "Dupes")
        touched = self.collection.upsert_user_standard_sections(
            std.id, [("9.1", "first text"), ("9.1", "second text"), ("9.2", "x")]
        )
        rows = {
            r.section_id: r
            for r in self.collection.get_user_standard_sections(std.id, self.user.id)
        }
        self.assertEqual(sorted(rows), ["9.1", "9.2"])
        self.assertEqual(rows["9.1"].section_text, "second text")
        self.assertEqual(touched, 3)

    def test_confirming_a_different_cre_clears_the_jobs_confidence(self) -> None:
        run_mapping(
            self.standard.id,
            self.collection,
            components=_components(self.by_text, self.conf),
            config=_config(),
        )
        # 1.2's candidate is salt at 0.42; the user picks nonce instead
        row = self._rows()["1.2"]
        self.collection.confirm_section_mapping(row.id, self.nonce.id, self.user.id)
        self.assertIsNone(self._rows()["1.2"].confidence)
        # confirming the job's own candidate keeps the score it was computed for
        row = self._rows()["1.1"]
        self.collection.confirm_section_mapping(row.id, self.nonce.id, self.user.id)
        self.assertEqual(self._rows()["1.1"].confidence, 0.95)

    def test_job_write_cannot_overwrite_a_decision_made_after_it_loaded(self) -> None:
        """The status guard is in the UPDATE, so a user decision that lands
        between the job's read and its write is the one that survives."""
        row = self._rows()["1.1"]
        self.collection.confirm_section_mapping(row.id, self.salt.id, self.user.id)
        moved = self.collection.set_section_mapping(
            row.id,
            cre_db_id=self.nonce.id,
            confidence=0.99,
            status=SectionStatus.AUTO_MAPPED.value,
        )
        self.assertFalse(moved)
        after = self._rows()["1.1"]
        self.assertEqual(after.status, SectionStatus.USER_CONFIRMED.value)
        self.assertEqual(after.cre_db_id, self.salt.id)

    def test_job_write_moves_a_pending_row(self) -> None:
        row = self._rows()["1.1"]
        moved = self.collection.set_section_mapping(
            row.id,
            cre_db_id=self.nonce.id,
            confidence=0.9,
            status=SectionStatus.AUTO_MAPPED.value,
        )
        self.assertTrue(moved)
        self.assertEqual(self._rows()["1.1"].status, SectionStatus.AUTO_MAPPED.value)

    def test_partial_failure_is_raised_so_rq_records_it(self) -> None:
        ok = MappingSummary(standard_id="s", threshold=0.8, considered=2, auto_mapped=2)
        self.assertIs(check_complete(ok), ok)
        bad = MappingSummary(
            standard_id="s", threshold=0.8, considered=2, auto_mapped=1, errored=1
        )
        with self.assertRaises(MappingPartialFailure) as caught:
            check_complete(bad)
        self.assertIs(caught.exception.summary, bad)
        self.assertIn("1 of 2", str(caught.exception))

    def test_default_queue_is_one_the_stock_worker_listens_to(self) -> None:
        from application import worker

        self.assertIn(DEFAULT_QUEUE, worker.DEFAULT_LISTEN)

    def test_empty_status_list_reads_nothing(self) -> None:
        self.assertEqual(
            self.collection.get_user_standard_sections_by_status(self.standard.id, []),
            [],
        )

    def test_same_name_for_two_users_is_two_rows_and_duplicate_for_one_user_fails(
        self,
    ) -> None:
        other_std = self.collection.create_user_standard(self.other.id, "My Policy")
        self.assertNotEqual(other_std.id, self.standard.id)
        self.assertEqual(len(self.collection.get_user_standards(self.user.id)), 1)
        from sqlalchemy.exc import IntegrityError

        with self.assertRaises(IntegrityError):
            self.collection.create_user_standard(self.user.id, "My Policy")
        sqla.session.rollback()


if __name__ == "__main__":
    unittest.main()
