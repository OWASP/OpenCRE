import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils.librarian.emitter import AUTO_LINK_TYPE
from application.utils.oie_scheduler import graph_filer

AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _envelope(
    chunk_id,
    *,
    repo="OWASP/www-project-foo",
    cre_ids=("111-111",),
    confidence=0.95,
    path="docs/auth.md",
    title="Authentication",
):
    return {
        "schema_version": "0.2.0",
        "chunk_id": chunk_id,
        "artifact_id": f"art:{path}",
        "pipeline_run_id": "run-1",
        "classified_at": AT.isoformat(),
        "status": "linked",
        "knowledge": {
            "text": "Use MFA.",
            "source": {
                "type": "github",
                "repo": repo,
                "commit_sha": "abcdef1234567",
                "committed_at": AT.isoformat(),
            },
            "locator": {
                "kind": "repo_path",
                "id": path,
                "path": path,
                "title": title,
            },
            "security_summary": "MFA guidance",
        },
        "retrieval": {
            "retriever": "test",
            "candidates": [],
            "reranked": [],
            "threshold": 0.8,
        },
        "links": [
            {"cre_id": c, "link_type": AUTO_LINK_TYPE, "confidence": confidence}
            for c in cre_ids
        ],
        "update_detection": {"is_update": False},
    }


class GraphFilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.collection.add_cre(
            defs.CRE(id="111-111", name="Authentication", description="d")
        )
        self.collection.add_cre(
            defs.CRE(id="222-222", name="Sessions", description="d")
        )

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _decision(self, chunk_id, envelope=None, *, status="linked", run="run-1"):
        sqla.session.add(
            db.DecisionQueueItem(
                chunk_id=chunk_id,
                artifact_id="art",
                pipeline_run_id=run,
                schema_version="0.2.0",
                status=status,
                confidence=0.9,
                envelope=envelope if envelope is not None else _envelope(chunk_id),
            )
        )
        sqla.session.commit()

    def _file(self, **kw):
        kw.setdefault("floor", 0.9)
        return graph_filer.file_linked_decisions(self.collection, now=AT, **kw)

    def test_confident_link_files_node_and_edge_and_consumes_row(self) -> None:
        self._decision("c1")
        res = self._file()
        self.assertEqual((res.considered, res.filed, res.links_added), (1, 1, 1))
        self.assertTrue(res.graph_changed)
        self.assertEqual(res.standards, ["OWASP/www-project-foo"])

        node = sqla.session.query(db.Node).one()
        self.assertEqual(node.name, "OWASP/www-project-foo")
        self.assertEqual(node.section, "Authentication")
        self.assertEqual(node.section_id, "docs/auth.md")
        self.assertIn("blob/abcdef1234567/docs/auth.md", node.link)
        link = sqla.session.query(db.Links).one()
        self.assertEqual(link.type, defs.LinkTypes.AutomaticallyLinkedTo.value)
        cre = sqla.session.get(db.CRE, link.cre)
        self.assertEqual(cre.external_id, "111-111")
        row = sqla.session.query(db.DecisionQueueItem).one()
        self.assertIsNotNone(row.consumed_at)

    def test_below_floor_is_dropped_but_left_unconsumed(self) -> None:
        self._decision("c1", _envelope("c1", confidence=0.85))
        res = self._file(floor=0.9)
        self.assertEqual((res.filed, res.below_floor, res.links_added), (0, 1, 0))
        self.assertFalse(res.graph_changed)
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_lowering_the_floor_later_files_the_same_row(self) -> None:
        self._decision("c1", _envelope("c1", confidence=0.85))
        self._file(floor=0.9)
        res = self._file(floor=0.8)
        self.assertEqual(res.filed, 1)

    def test_kill_switch_touches_nothing(self) -> None:
        self._decision("c1")
        res = self._file(enabled=False)
        self.assertFalse(res.enabled)
        self.assertEqual(res.considered, 0)
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_dry_run_reports_without_writing(self) -> None:
        self._decision("c1")
        res = self._file(dry_run=True)
        self.assertEqual(res.filed, 1)
        self.assertEqual(res.links_added, 0)
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_review_rows_and_consumed_rows_are_ignored(self) -> None:
        self._decision("c1", status="review_required")
        self._decision("c2")
        self._file()
        res = self._file()
        self.assertEqual(res.considered, 0)

    def test_rerun_is_idempotent(self) -> None:
        self._decision("c1")
        self._file()
        again = self._file()
        self.assertEqual(again.considered, 0)
        self.assertEqual(sqla.session.query(db.Links).count(), 1)

    def test_existing_edge_is_not_overwritten(self) -> None:
        self._decision("c1")
        node = self.collection.add_node(
            defs.Standard(
                name="OWASP/www-project-foo",
                section="Authentication",
                sectionID="docs/auth.md",
            )
        )
        cre = sqla.session.query(db.CRE).filter_by(external_id="111-111").one()
        self.collection.add_link(cre=cre, node=node, ltype=defs.LinkTypes.LinkedTo)
        res = self._file()
        self.assertEqual((res.links_added, res.links_already_present), (0, 1))
        self.assertFalse(res.graph_changed)
        self.assertEqual(
            sqla.session.query(db.Links).one().type, defs.LinkTypes.LinkedTo.value
        )

    def test_unknown_cre_is_not_filed_and_stays_unconsumed(self) -> None:
        self._decision("c1", _envelope("c1", cre_ids=("999-999",)))
        res = self._file()
        self.assertEqual((res.unknown_cre, res.filed), (1, 0))
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_multiple_cres_and_only_the_sure_ones(self) -> None:
        env = _envelope("c1", cre_ids=("111-111", "222-222"))
        env["links"][1]["confidence"] = 0.5
        self._decision("c1", env)
        res = self._file()
        self.assertEqual(res.links_added, 1)

    def test_standard_repos_are_skipped(self) -> None:
        self._decision("c1", _envelope("c1", repo="OWASP/ASVS"))
        res = self._file(skip_repos={"owasp/asvs"})
        self.assertEqual((res.skipped_standard_repo, res.filed), (1, 0))
        self.assertEqual(sqla.session.query(db.Node).count(), 0)

    def test_invalid_envelope_is_counted_and_left_alone(self) -> None:
        self._decision("c1", {"status": "linked", "garbage": True})
        res = self._file()
        self.assertEqual((res.invalid, res.filed), (1, 0))
        self.assertIsNone(sqla.session.query(db.DecisionQueueItem).one().consumed_at)

    def test_two_chunks_in_the_same_section_share_one_node(self) -> None:
        self._decision("c1", _envelope("c1"))
        self._decision("c2", _envelope("c2", cre_ids=("222-222",)))
        res = self._file()
        self.assertEqual(res.filed, 2)
        self.assertEqual(sqla.session.query(db.Node).count(), 1)
        self.assertEqual(sqla.session.query(db.Links).count(), 2)


if __name__ == "__main__":
    unittest.main()
