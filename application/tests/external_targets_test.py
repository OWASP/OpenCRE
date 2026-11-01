import os
import unittest
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.utils.admin_panel import external_targets as et
from application.utils.admin_panel import service
from application.utils.comprehension import external as ext
from application.utils.comprehension import link_suggestions as ls

CHUNKS = {
    "OWASP/foo": [
        (
            "README.md",
            0,
            "[website](https://foo-conf.org/) and [chan](https://www.youtube.com/@FooSec)",
        )
    ]
}


def suggestions():
    return ls.suggest_links(CHUNKS)


class TestExternalTargets(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_upsert_creates_disabled_suggestions(self) -> None:
        res = et.upsert_suggestions(suggestions())
        self.assertEqual(sorted(res["created"]), ["foo-conf-org", "yt-foosec"])
        row = sqla.session.query(db.IngestionTarget).get("foo-conf-org")
        self.assertFalse(row.enabled)
        self.assertEqual(row.kind, ext.KIND_SITE)
        spec = ext.spec_from_target(row)
        self.assertEqual(spec.status, ext.STATUS_SUGGESTED)
        self.assertEqual(spec.found_in[0]["repo"], "OWASP/foo")
        self.assertEqual(
            [s["id"] for s in et.list_suggestions()][0]
            in ("foo-conf-org", "yt-foosec"),
            True,
        )
        self.assertEqual(ext.load_specs(sqla.session), [])

    def test_upsert_merges_provenance_and_keeps_best_score(self) -> None:
        et.upsert_suggestions(suggestions())
        more = ls.suggest_links(
            {"OWASP/bar": [("a/b.md", 0, "https://foo-conf.org/x")]}
        )
        res = et.upsert_suggestions(more)
        self.assertEqual(res["merged"], ["foo-conf-org"])
        s = next(x for x in et.list_suggestions() if x["id"] == "foo-conf-org")
        self.assertEqual(
            {f["repo"] for f in s["spec"]["found_in"]}, {"OWASP/foo", "OWASP/bar"}
        )
        self.assertGreaterEqual(s["score"], 5.0)
        self.assertEqual(len(et.list_external()), 2)

    def test_approved_and_rejected_never_overwritten_or_resuggested(self) -> None:
        et.upsert_suggestions(suggestions())
        et.accept("foo-conf-org", {"max_pages": 10})
        et.reject("yt-foosec")
        res = et.upsert_suggestions(suggestions())
        self.assertEqual(res["created"], [])
        self.assertEqual(sorted(res["skipped"]), ["foo-conf-org", "yt-foosec"])
        row = sqla.session.query(db.IngestionTarget).get("foo-conf-org")
        self.assertEqual(ext.spec_from_target(row).max_pages, 10)
        self.assertEqual(et.list_suggestions(), [])

    def test_other_id_same_host_not_resuggested(self) -> None:
        et.add_manual(
            {
                "id": "my-foo",
                "name": "Foo",
                "start_urls": ["https://docs.foo-conf.org/"],
            }
        )
        res = et.upsert_suggestions(suggestions())
        self.assertEqual(res["created"], ["yt-foosec"])

    def test_accept_applies_overrides_and_validates(self) -> None:
        et.upsert_suggestions(suggestions())
        out = et.accept(
            "foo-conf-org",
            {
                "start_urls": ["https://foo-conf.org/schedule"],
                "allow_prefixes": ["https://foo-conf.org/"],
                "max_pages": 50,
                "refresh_days": 7,
                "weight": 1.5,
                "aliases": ["Foo Conf"],
                "status": "suggested",  # not editable
                "kind": "youtube_channel",  # not editable
            },
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["status"], ext.STATUS_APPROVED)
        self.assertEqual(out["kind"], ext.KIND_SITE)
        [spec] = ext.load_specs(sqla.session)
        self.assertEqual(spec.start_urls, ["https://foo-conf.org/schedule"])
        self.assertEqual((spec.max_pages, spec.refresh_days, spec.weight), (50, 7, 1.5))
        with self.assertRaises(ValueError):
            et.accept("yt-foosec", {"weight": 99})
        with self.assertRaises(KeyError):
            et.accept("missing")

    def test_reject_keeps_row_disabled(self) -> None:
        et.upsert_suggestions(suggestions())
        out = et.reject("foo-conf-org")
        self.assertEqual(out["status"], ext.STATUS_REJECTED)
        self.assertFalse(out["enabled"])
        self.assertIsNotNone(sqla.session.query(db.IngestionTarget).get("foo-conf-org"))

    def test_add_manual(self) -> None:
        out = et.add_manual({"name": "X", "start_urls": ["https://www.x-site.org/a"]})
        self.assertEqual(out["id"], "x-site-org")
        self.assertEqual(out["status"], ext.STATUS_APPROVED)
        with self.assertRaises(ValueError):
            et.add_manual({"name": "X", "start_urls": ["https://x-site.org/"]})
        with self.assertRaises(ValueError):
            et.add_manual({"name": "bad", "start_urls": ["ftp://x"]})

    def test_external_targets_invisible_to_oie_selection(self) -> None:
        et.upsert_suggestions(suggestions())
        et.accept("foo-conf-org")
        service.add_target(target_id="src", kind="import_source", name="src")
        ids = [t["id"] for t in service.list_targets()]
        self.assertIn("src", ids)
        self.assertNotIn("foo-conf-org", ids)
        self.assertNotIn("yt-foosec", ids)
        with self.assertRaises(KeyError):
            service.start_ingestion(target_id="foo-conf-org")

    def test_external_rows_do_not_block_yaml_seed(self) -> None:
        et.upsert_suggestions(suggestions())
        service.seed_targets_from_yaml_if_empty()
        kinds = {r.kind for r in sqla.session.query(db.IngestionTarget).all()}
        self.assertIn("oie_repo", kinds)


class TestExternalRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"
        et.upsert_suggestions(suggestions())

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_list_accept_reject_add(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/external")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(
                {e["id"] for e in r.get_json()["external"]},
                {"foo-conf-org", "yt-foosec"},
            )
            r = c.post("/admin/external/foo-conf-org/accept", json={"max_pages": 20})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["status"], "approved")
            self.assertEqual(r.get_json()["spec"]["max_pages"], 20)
            r = c.post("/admin/external/foo-conf-org/accept", json={"max_pages": 0})
            self.assertEqual(r.status_code, 400)
            r = c.post("/admin/external/yt-foosec/reject")
            self.assertEqual(r.get_json()["status"], "rejected")
            self.assertEqual(
                c.post("/admin/external/nope/accept", json={}).status_code, 404
            )
            self.assertEqual(c.post("/admin/external/nope/reject").status_code, 404)
            r = c.post(
                "/admin/external", json={"name": "N", "start_urls": ["https://n.org/"]}
            )
            self.assertEqual(r.status_code, 201)
            self.assertEqual(
                c.post(
                    "/admin/external",
                    json={"name": "N", "start_urls": ["https://n.org/"]},
                ).status_code,
                400,
            )
            ids = [t["id"] for t in c.get("/admin/targets").get_json()["targets"]]
            self.assertNotIn("n-org", ids)

    def test_requires_login_or_imports(self) -> None:
        with self.app.test_client() as c:
            self.assertNotEqual(c.get("/admin/external").status_code, 200)


if __name__ == "__main__":
    unittest.main()
