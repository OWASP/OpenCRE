"""embed_meta_if_enabled: the opt-in push of agent meta into shared embeddings."""

from __future__ import annotations

import os
import tempfile
import unittest
from typing import Any, List
from unittest.mock import patch

import sqlalchemy as sa

from application import create_app, sqla  # type: ignore
from application.database import db
from application.utils.owasp_agent.embed_sync import embed_meta_if_enabled
from application.utils.owasp_agent.index_store import IndexStore
from application.utils.owasp_agent.lane_similarity import CHANNEL_AGENT, CHANNEL_CRE
from application.utils.owasp_agent.models import Chapter, Project
from application.utils.owasp_agent.sync import SyncReport


def _embed(text: str) -> List[float]:
    return [float(len(text) % 7), 1.0, 0.5]


def _boom(text: str) -> List[float]:
    raise RuntimeError("embedding backend down")


class TestEmbedMetaIfEnabled(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.database = db.Node_collection()

        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(os.path.join(self.tmp.name, "agent.sqlite"))
        self.store.upsert_chapter(
            Chapter(
                key="los-angeles",
                name="OWASP Los Angeles",
                city="Los Angeles",
                url="https://nest.example/la",
                source="nest",
            )
        )
        self.store.upsert_project(
            Project(
                key="zap",
                name="ZAP",
                tags=["appsec"],
                source="nest",
                url="https://nest.example/zap",
            )
        )
        self.report = SyncReport()

    def tearDown(self) -> None:
        self.store.engine.dispose()
        self.tmp.cleanup()
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def _agent_rows(self) -> List[Any]:
        return list(
            sqla.session.query(db.Embeddings).filter_by(source_channel=CHANNEL_AGENT)
        )

    def _sync_log(self) -> List[Any]:
        with self.store.engine.connect() as conn:
            return list(
                conn.execute(
                    sa.text(
                        "SELECT source, status, detail FROM sync_log "
                        "WHERE source = 'meta_embeddings'"
                    )
                )
            )

    def test_flag_off_returns_false_and_touches_nothing(self) -> None:
        calls: List[str] = []

        def spy(text: str) -> List[float]:
            calls.append(text)
            return _embed(text)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWASP_AGENT_EMBED_META", None)
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=spy
            )

        self.assertFalse(ran)
        self.assertEqual(calls, [])
        self.assertEqual(self._agent_rows(), [])
        self.assertEqual(self._sync_log(), [])
        self.assertEqual(self.report.errors, [])

    def test_flag_value_zero_is_off(self) -> None:
        with patch.dict(os.environ, {"OWASP_AGENT_EMBED_META": "0"}):
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=_embed
            )
        self.assertFalse(ran)
        self.assertEqual(self._agent_rows(), [])

    def test_flag_on_writes_agent_rows_and_logs_ok(self) -> None:
        for flag in ("1", "true", "yes"):
            with self.subTest(flag=flag):
                with patch.dict(os.environ, {"OWASP_AGENT_EMBED_META": flag}):
                    ran = embed_meta_if_enabled(
                        self.store,
                        self.report,
                        database=self.database,
                        embed_fn=_embed,
                    )
                self.assertTrue(ran)

        rows = self._agent_rows()
        urls = {r.embeddings_url for r in rows}
        self.assertIn("owasp-agent://meta/chapter/los-angeles/nest", urls)
        self.assertIn("owasp-agent://meta/project/zap/nest", urls)
        for row in rows:
            self.assertEqual(row.source_channel, CHANNEL_AGENT)
            self.assertIsNone(row.cre_id)
            self.assertIsNone(row.node_id)
            self.assertEqual(row.embedding_dim, 3)
        logged = self._sync_log()
        self.assertEqual(len(logged), 3)
        self.assertTrue(all(entry[1] == "ok" for entry in logged))
        self.assertEqual(self.report.errors, [])

    def test_embed_failure_is_recorded_not_raised(self) -> None:
        with patch.dict(os.environ, {"OWASP_AGENT_EMBED_META": "1"}):
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=_boom
            )

        self.assertFalse(ran)
        self.assertEqual(len(self.report.errors), 1)
        self.assertTrue(self.report.errors[0].startswith("meta_embeddings: "))
        self.assertIn("embedding backend down", self.report.errors[0])
        logged = self._sync_log()
        self.assertEqual([entry[1] for entry in logged], ["error"])
        self.assertEqual(self._agent_rows(), [])


class TestEmbedDimensionGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.database = db.Node_collection()

        self.tmp = tempfile.TemporaryDirectory()
        self.store = IndexStore(os.path.join(self.tmp.name, "agent.sqlite"))
        self.store.upsert_project(
            Project(
                key="zap",
                name="ZAP",
                tags=["appsec"],
                source="nest",
                url="https://nest.example/zap",
            )
        )
        self.report = SyncReport()

    def tearDown(self) -> None:
        self.store.engine.dispose()
        self.tmp.cleanup()
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def _add_cre_graph_row(self, dim: int) -> None:
        sqla.session.add(
            db.Embeddings(
                doc_type="CRE",
                embeddings_url="https://example.test/cre/1",
                embeddings_content="existing cre row",
                embedding_model_id="test/model",
                embedding_dim=dim,
                embedding_vec="[" + ",".join(["0.5"] * dim) + "]",
                source_channel=CHANNEL_CRE,
            )
        )
        sqla.session.commit()

    def _agent_count(self) -> int:
        return int(
            sqla.session.query(db.Embeddings)
            .filter_by(source_channel=CHANNEL_AGENT)
            .count()
        )

    def test_refuses_vector_whose_length_differs_from_existing_rows(self) -> None:
        self._add_cre_graph_row(dim=4)
        with patch.dict(os.environ, {"OWASP_AGENT_EMBED_META": "1"}):
            os.environ.pop("CRE_EMBED_EXPECTED_DIM", None)
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=_embed
            )

        self.assertFalse(ran)
        self.assertEqual(self._agent_count(), 0)
        self.assertEqual(len(self.report.errors), 1)
        self.assertIn("dimension mismatch", self.report.errors[0])

    def test_accepts_vector_matching_existing_rows(self) -> None:
        self._add_cre_graph_row(dim=3)
        with patch.dict(os.environ, {"OWASP_AGENT_EMBED_META": "1"}):
            os.environ.pop("CRE_EMBED_EXPECTED_DIM", None)
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=_embed
            )

        self.assertTrue(ran)
        self.assertGreater(self._agent_count(), 0)
        self.assertEqual(self.report.errors, [])

    def test_expected_dim_env_wins_on_an_empty_table(self) -> None:
        with patch.dict(
            os.environ,
            {"OWASP_AGENT_EMBED_META": "1", "CRE_EMBED_EXPECTED_DIM": "5"},
        ):
            ran = embed_meta_if_enabled(
                self.store, self.report, database=self.database, embed_fn=_embed
            )

        self.assertFalse(ran)
        self.assertEqual(self._agent_count(), 0)
        self.assertIn("dimension mismatch", self.report.errors[0])


if __name__ == "__main__":
    unittest.main()
