import os
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils.admin_panel import oie_review
from application.utils.oie_scheduler import graph_filer

AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _envelope(chunk_id, *, status="linked", cre_ids=("111-111",), confidence=0.95):
    links = [
        {
            "cre_id": c,
            "link_type": "Automatically linked to",
            "confidence": confidence,
        }
        for c in cre_ids
    ]
    env = {
        "schema_version": "0.2.0",
        "chunk_id": chunk_id,
        "artifact_id": "art:docs/auth.md",
        "pipeline_run_id": "run-1",
        "status": status,
        "knowledge": {
            "text": "Use MFA.",
            "source": {
                "type": "github",
                "repo": "OWASP/www-project-foo",
                "commit_sha": "abcdef1234567",
                "committed_at": AT.isoformat(),
            },
            "locator": {
                "kind": "repo_path",
                "id": "docs/auth.md",
                "path": "docs/auth.md",
                "title": "Authentication",
            },
            "security_summary": "MFA guidance",
        },
        "retrieval": {
            "retriever": "test",
            "candidates": [],
            "reranked": [],
            "threshold": 0.8,
        },
        "update_detection": {"is_update": False},
    }
    if status == "linked":
        env["classified_at"] = AT.isoformat()
        env["links"] = links
    else:
        env["review_id"] = f"rev-{chunk_id}"
        env["created_at"] = AT.isoformat()
        env["reason_code"] = "BELOW_THRESHOLD"
        env["suggested_links"] = links
    return env


def _web_envelope(chunk_id, *, status="review_required", cre_ids=("111-111",)):
    env = _envelope(chunk_id, status=status, cre_ids=cre_ids)
    env["knowledge"]["source"] = {
        "type": "url",
        "url": "https://www.slsa.dev/spec/v1.0/levels",
        "committed_at": AT.isoformat(),
    }
    env["knowledge"]["locator"] = {
        "kind": "url",
        "id": "build-l2",
        "url": "https://www.slsa.dev/spec/v1.0/levels#build-l2",
        "title": "Build L2",
    }
    return env


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        for cid, name in (
            ("111-111", "Authentication"),
            ("222-222", "Sessions"),
            ("333-333", "Logging"),
        ):
            self.collection.add_cre(defs.CRE(id=cid, name=name, description="d"))

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _decision(self, chunk_id, *, status="linked", **kw):
        row = db.DecisionQueueItem(
            chunk_id=chunk_id,
            artifact_id="art",
            pipeline_run_id="run-1",
            schema_version="0.2.0",
            status=status,
            confidence=0.7,
            envelope=_envelope(chunk_id, status=status, **kw),
        )
        sqla.session.add(row)
        sqla.session.commit()
        return row.id

    def _web_decision(self, chunk_id="w1", **kw):
        row = db.DecisionQueueItem(
            chunk_id=chunk_id,
            artifact_id="art",
            pipeline_run_id="run-1",
            schema_version="0.2.0",
            status="review_required",
            confidence=0.7,
            envelope=_web_envelope(chunk_id, **kw),
        )
        sqla.session.add(row)
        sqla.session.commit()
        return row.id

    def _link_cres(self):
        out = []
        for link in sqla.session.query(db.Links).all():
            cre = sqla.session.get(db.CRE, link.cre)
            out.append((cre.external_id, link.type))
        return sorted(out)

    # ---- repointing already auto-filed links --------------------------
    def _auto_file(self):
        self._decision("c1")
        graph_filer.file_linked_decisions(self.collection, floor=0.9, now=AT)
        return sqla.session.query(db.Node).one().id


class OieReviewTest(_Fixture):
    # ---- listing -------------------------------------------------------
    def test_list_returns_unconsumed_rows_with_candidates(self) -> None:
        self._decision("c1")
        self._decision("c2", status="review_required", cre_ids=("222-222",))
        out = oie_review.list_decisions()
        self.assertEqual(out["total"], 2)
        by_chunk = {r["chunk_id"]: r for r in out["items"]}
        self.assertEqual(by_chunk["c1"]["candidates"][0]["cre_id"], "111-111")
        self.assertEqual(by_chunk["c1"]["candidates"][0]["cre_name"], "Authentication")
        self.assertEqual(by_chunk["c2"]["status"], "review_required")
        self.assertEqual(by_chunk["c1"]["review"], None)

    def test_list_filters_by_status(self) -> None:
        self._decision("c1")
        self._decision("c2", status="review_required")
        out = oie_review.list_decisions(status="review_required")
        self.assertEqual([r["chunk_id"] for r in out["items"]], ["c2"])

    # ---- approve / reject / repoint -----------------------------------
    def test_approve_files_node_with_reviewer_set_link_and_consumes(self) -> None:
        did = self._decision("c1", status="review_required")
        res = oie_review.review_decision(did, "approve", reviewer="a@x.org")
        self.assertEqual(res["links_added"], 1)
        self.assertEqual(
            self._link_cres(), [("111-111", defs.LinkTypes.LinkedTo.value)]
        )
        node = sqla.session.query(db.Node).one()
        self.assertIn(oie_review.REVIEWED_TAG, node.tags)
        row = sqla.session.get(db.DecisionQueueItem, did)
        self.assertIsNotNone(row.consumed_at)

    def test_repoint_overrides_proposed_cres(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(
            did, "repoint", reviewer="a@x.org", cre_ids=["222-222"]
        )
        self.assertEqual(
            self._link_cres(), [("222-222", defs.LinkTypes.LinkedTo.value)]
        )

    def test_repoint_can_accept_several_cres(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(
            did, "repoint", reviewer="a@x.org", cre_ids=["222-222", "333-333"]
        )
        self.assertEqual(len(self._link_cres()), 2)

    def test_repoint_requires_known_cre(self) -> None:
        did = self._decision("c1")
        with self.assertRaises(ValueError):
            oie_review.review_decision(
                did, "repoint", reviewer="a", cre_ids=["999-999"]
            )
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertIsNone(sqla.session.get(db.DecisionQueueItem, did).consumed_at)

    def test_repoint_requires_cre_ids(self) -> None:
        did = self._decision("c1")
        with self.assertRaises(ValueError):
            oie_review.review_decision(did, "repoint", reviewer="a")

    def test_reject_writes_nothing_and_consumes(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(did, "reject", reviewer="a", note="wrong topic")
        self.assertEqual(sqla.session.query(db.Node).count(), 0)
        self.assertIsNotNone(sqla.session.get(db.DecisionQueueItem, did).consumed_at)

    def test_second_review_of_same_row_is_refused(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(did, "approve", reviewer="a")
        with self.assertRaises(ValueError):
            oie_review.review_decision(did, "approve", reviewer="a")
        self.assertEqual(len(self._link_cres()), 1)

    def test_unknown_decision_and_action(self) -> None:
        with self.assertRaises(KeyError):
            oie_review.review_decision("nope", "approve", reviewer="a")
        did = self._decision("c1")
        with self.assertRaises(ValueError):
            oie_review.review_decision(did, "frobnicate", reviewer="a")

    def test_review_is_recorded_for_audit(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(
            did, "repoint", reviewer="a@x.org", cre_ids=["222-222"], note="n"
        )
        rows = sqla.session.query(db.DecisionReview).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, "repoint")
        self.assertEqual(rows[0].reviewer, "a@x.org")
        self.assertEqual(rows[0].payload["proposed_cre_ids"], ["111-111"])
        self.assertEqual(rows[0].payload["final_cre_ids"], ["222-222"])
        listed = oie_review.list_decisions(include_consumed=True)["items"][0]
        self.assertEqual(listed["review"]["action"], "repoint")

    def test_list_filed_shows_auto_filed_nodes_and_links(self) -> None:
        self._auto_file()
        out = oie_review.list_filed()
        self.assertEqual(out["total"], 1)
        item = out["items"][0]
        self.assertEqual(item["links"][0]["cre_id"], "111-111")
        self.assertEqual(
            item["links"][0]["type"], defs.LinkTypes.AutomaticallyLinkedTo.value
        )

    def test_repoint_filed_replaces_link_and_keeps_audit(self) -> None:
        node_id = self._auto_file()
        oie_review.repoint_filed_link(
            node_id, "111-111", "222-222", reviewer="a@x.org", note="wrong"
        )
        self.assertEqual(
            self._link_cres(), [("222-222", defs.LinkTypes.LinkedTo.value)]
        )
        audit = sqla.session.query(db.DecisionReview).one()
        self.assertEqual(audit.action, "repoint_filed")
        self.assertEqual(audit.payload["from_cre_id"], "111-111")
        self.assertEqual(audit.payload["to_cre_id"], "222-222")
        self.assertEqual(audit.payload["from_type"], "Automatically linked to")

    def test_repoint_filed_errors(self) -> None:
        node_id = self._auto_file()
        with self.assertRaises(KeyError):
            oie_review.repoint_filed_link("nope", "111-111", "222-222", reviewer="a")
        with self.assertRaises(ValueError):  # no such existing link
            oie_review.repoint_filed_link(node_id, "333-333", "222-222", reviewer="a")
        with self.assertRaises(ValueError):  # unknown target CRE
            oie_review.repoint_filed_link(node_id, "111-111", "999-999", reviewer="a")
        with self.assertRaises(ValueError):  # no-op
            oie_review.repoint_filed_link(node_id, "111-111", "111-111", reviewer="a")
        self.assertEqual(
            self._link_cres(),
            [("111-111", defs.LinkTypes.AutomaticallyLinkedTo.value)],
        )

    def test_repoint_filed_can_be_chained(self) -> None:
        node_id = self._auto_file()
        oie_review.repoint_filed_link(node_id, "111-111", "222-222", reviewer="a")
        oie_review.repoint_filed_link(node_id, "222-222", "333-333", reviewer="a")
        self.assertEqual([c for c, _ in self._link_cres()], ["333-333"])

    # ---- website sources ----------------------------------------------
    def test_website_decision_lists_suggested_standard_name(self) -> None:
        self._web_decision()
        item = oie_review.list_decisions()["items"][0]
        self.assertFalse(item["invalid"])
        self.assertIsNone(item["source"]["repo"])
        self.assertEqual(item["source"]["standard_name"], "slsa.dev")
        self.assertEqual(
            item["source"]["hyperlink"],
            "https://www.slsa.dev/spec/v1.0/levels#build-l2",
        )

    def test_website_decision_files_under_host_by_default(self) -> None:
        did = self._web_decision()
        oie_review.review_decision(did, "approve", reviewer="a")
        node = sqla.session.query(db.Node).one()
        self.assertEqual(node.name, "slsa.dev")
        self.assertEqual(node.section, "Build L2")
        self.assertEqual(node.section_id, "build-l2")
        self.assertEqual(node.link, "https://www.slsa.dev/spec/v1.0/levels#build-l2")
        self.assertEqual(
            self._link_cres(), [("111-111", defs.LinkTypes.LinkedTo.value)]
        )

    def test_website_decision_standard_name_override(self) -> None:
        did = self._web_decision()
        oie_review.review_decision(did, "approve", reviewer="a", standard_name="SLSA")
        self.assertEqual(sqla.session.query(db.Node).one().name, "SLSA")

    def test_repo_decision_accepts_standard_name_override(self) -> None:
        did = self._decision("c1")
        oie_review.review_decision(did, "approve", reviewer="a", standard_name="Custom")
        self.assertEqual(sqla.session.query(db.Node).one().name, "Custom")

    # ---- tags ----------------------------------------------------------
    def test_review_swaps_only_the_auto_filed_tag(self) -> None:
        node_id = self._auto_file()
        node = sqla.session.get(db.Node, node_id)
        node.tags = f"{graph_filer.AUTO_FILED_TAG},keep-me,other"
        sqla.session.commit()
        self._decision("c2")  # same section as c1 -> same node identity
        did = sqla.session.query(db.DecisionQueueItem).filter_by(chunk_id="c2").one().id
        oie_review.review_decision(did, "repoint", reviewer="a", cre_ids=["222-222"])
        tags = sqla.session.get(db.Node, node_id).tags.split(",")
        self.assertIn("keep-me", tags)
        self.assertIn("other", tags)
        self.assertIn(oie_review.REVIEWED_TAG, tags)
        self.assertNotIn(graph_filer.AUTO_FILED_TAG, tags)
        self.assertEqual(len(tags), len(set(tags)))

    # ---- CRE search ----------------------------------------------------
    def test_search_cres_by_name_and_id(self) -> None:
        by_name = oie_review.search_cres("sess")
        self.assertEqual([c["cre_id"] for c in by_name], ["222-222"])
        self.assertEqual(by_name[0]["name"], "Sessions")
        by_id = oie_review.search_cres("333-333")
        self.assertEqual([c["cre_id"] for c in by_id], ["333-333"])

    def test_search_cres_rules(self) -> None:
        self.assertEqual(oie_review.search_cres(""), [])
        self.assertEqual(oie_review.search_cres("a"), [])  # too short
        self.assertEqual(oie_review.search_cres("zzzzzz"), [])
        self.assertEqual(oie_review.search_cres("%"), [])  # wildcard is literal
        self.assertEqual(len(oie_review.search_cres("ion")), 2)
        self.assertEqual(len(oie_review.search_cres("ion", limit=1)), 1)


_ENV = {
    "NO_LOGIN": "0",
    "CRE_ALLOW_IMPORT": "1",
    "CRE_ENABLE_LOGIN": "1",
    "LOGIN_ALLOWED_DOMAINS": "*",
    "LOGIN_ALLOWED_EMAILS": "admin@example.com",
    "FLASK_CONFIG": "development",
    "INSECURE_REQUESTS": "1",
}


class OieReviewRoutesTest(_Fixture):
    def _client(self, email="admin@example.com"):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["email"] = email
            sess["google_id"] = "g1"
        return client

    def test_non_admin_is_refused(self) -> None:
        with patch.dict(os.environ, _ENV, clear=False):
            # a refused request ends the session, so use a fresh client per route
            for path in ("/admin/oie/decisions", "/admin/oie/filed"):
                client = self._client("someone@example.com")
                self.assertEqual(client.get(path).status_code, 403, path)

    def test_list_review_and_csrf(self) -> None:
        did = self._decision("c1", status="review_required")
        with patch.dict(os.environ, _ENV, clear=False):
            client = self._client()
            token = client.get("/admin/config").get_json()["csrf_token"]
            listed = client.get("/admin/oie/decisions?status=review_required")
            self.assertEqual(listed.status_code, 200, listed.data)
            self.assertEqual(listed.get_json()["total"], 1)
            url = f"/admin/oie/decisions/{did}"
            body = {"action": "repoint", "cre_ids": ["222-222"]}
            self.assertEqual(client.post(url, json=body).status_code, 403)
            ok = client.post(url, json=body, headers={"X-CSRF-Token": token})
            self.assertEqual(ok.status_code, 200, ok.data)
            again = client.post(url, json=body, headers={"X-CSRF-Token": token})
            self.assertEqual(again.status_code, 400)
            gone = client.post(
                "/admin/oie/decisions/nope", json=body, headers={"X-CSRF-Token": token}
            )
            self.assertEqual(gone.status_code, 404)
        review = sqla.session.query(db.DecisionReview).one()
        self.assertEqual(review.reviewer, "admin@example.com")

    def test_repoint_filed_route(self) -> None:
        node_id = self._auto_file()
        with patch.dict(os.environ, _ENV, clear=False):
            client = self._client()
            token = client.get("/admin/config").get_json()["csrf_token"]
            filed = client.get("/admin/oie/filed").get_json()
            self.assertEqual(filed["total"], 1)
            bad = client.post(
                f"/admin/oie/filed/{node_id}/repoint",
                json={"from_cre_id": "111-111"},
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(bad.status_code, 400)
            ok = client.post(
                f"/admin/oie/filed/{node_id}/repoint",
                json={"from_cre_id": "111-111", "to_cre_id": "222-222"},
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(
            self._link_cres(), [("222-222", defs.LinkTypes.LinkedTo.value)]
        )

    def test_search_route_and_standard_name_through_route(self) -> None:
        did = self._web_decision()
        with patch.dict(os.environ, _ENV, clear=False):
            client = self._client()
            token = client.get("/admin/config").get_json()["csrf_token"]
            found = client.get("/admin/oie/cres/search?q=auth")
            self.assertEqual(found.status_code, 200, found.data)
            self.assertEqual(found.get_json()["items"][0]["cre_id"], "111-111")
            self.assertEqual(
                client.get("/admin/oie/cres/search").get_json()["items"], []
            )
            bad = client.post(
                f"/admin/oie/decisions/{did}",
                json={"action": "approve", "standard_name": 5},
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(bad.status_code, 400)
            ok = client.post(
                f"/admin/oie/decisions/{did}",
                json={"action": "approve", "standard_name": "SLSA"},
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(sqla.session.query(db.Node).one().name, "SLSA")


if __name__ == "__main__":
    unittest.main()
