import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from application import create_app, sqla
from application.database import db
from application.utils.admin_panel import external_targets as et
from application.utils.comprehension import event_seed as es
from application.utils.comprehension import external as ext

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def site(**kw):
    base = {
        "id": "x-conf-org",
        "name": "X Conf",
        "url": "https://x-conf.org/",
        "start_url": "https://x-conf.org/program",
        "kind": "regional",
        "year": 2026,
        "status": "candidate",
        "suggest": True,
        "needs_review": False,
        "review_reasons": [],
        "robots": {"generic_agents_allowed": True, "notes": "all allowed"},
    }
    base.update(kw)
    return base


class TestSeedFile(unittest.TestCase):
    def test_shipped_file_is_valid_and_big_enough(self) -> None:
        sites = es.load_sites()
        self.assertGreaterEqual(len(sites), 15)
        self.assertTrue(
            any(
                s["status"] == "registered" and "2026.owaspbenelux.eu" in s["url"]
                for s in sites
            )
        )
        self.assertTrue(es.candidates(sites))
        for s in sites:
            if s["needs_review"]:
                self.assertTrue(s["review_reasons"])

    def test_validation_rejects_bad_entries(self) -> None:
        for bad in (
            site(kind="galaxy"),
            site(start_url="ftp://x"),
            site(max_pages=500),
            site(year="2026"),
            site(needs_review=True, review_reasons=[]),
            site(robots={}),
        ):
            with self.assertRaises(ValueError):
                es.validate_site(bad)
        missing = site()
        del missing["name"]
        with self.assertRaises(ValueError):
            es.validate_site(missing)

    def test_duplicate_ids_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps({"sites": [site(), site()]}))
            with self.assertRaises(ValueError):
                es.load_sites(p)


class TestCandidates(unittest.TestCase):
    def test_defaults(self) -> None:
        c = es.to_candidate(site(), NOW)
        self.assertEqual(c["url"], "https://x-conf.org/program")
        self.assertEqual(c["allow_prefixes"], ["https://x-conf.org/"])
        self.assertEqual((c["max_depth"], c["max_pages"]), (2, 40))
        self.assertEqual(c["refresh_days"], 7)
        self.assertEqual(c["found_in"][0]["source"], "seed")
        self.assertIn("owasp-event-sites.md", c["found_in"][0]["page"])
        self.assertFalse(c["subdomain"])
        old = es.to_candidate(site(year=2024), NOW)
        self.assertEqual(old["refresh_days"], 30)
        sub = es.to_candidate(site(start_url="https://2025.x-conf.org/"), NOW)
        self.assertTrue(sub["subdomain"])
        self.assertIn(
            "needs-review",
            es.to_candidate(site(needs_review=True, review_reasons=["why"]), NOW)[
                "notes"
            ],
        )

    def test_registered_and_unsuggested_are_not_candidates(self) -> None:
        sites = [
            site(),
            site(id="a", status="registered"),
            site(id="b", suggest=False),
        ]
        self.assertEqual(len(es.candidates(sites, NOW)), 1)


class TestStore(unittest.TestCase):
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

    def _count(self) -> int:
        return sqla.session.query(db.IngestionTarget).count()

    def _register(self, host: str, status: str) -> None:
        cand = es.to_candidate(site(start_url=f"https://{host}/"), NOW)
        et.upsert_suggestions([cand])
        if status != ext.STATUS_SUGGESTED:
            row = sqla.session.query(db.IngestionTarget).get(
                es.link_suggestions.candidate_id(cand)
            )
            data = json.loads(row.spec_json)
            data["status"] = status
            row.spec_json = json.dumps(data)
            sqla.session.commit()

    def test_plan_writes_nothing(self) -> None:
        cands = es.candidates(es.load_sites(), NOW)
        plan = es.plan(cands, sqla.session)
        self.assertEqual(len(plan), len(cands))
        self.assertTrue(all(p["action"] == "create" for p in plan))
        self.assertEqual(self._count(), 0)

    def test_apply_creates_disabled_suggestions(self) -> None:
        cands = es.candidates(
            [site(), site(id="y", url="https://y.org/", start_url="https://y.org/")],
            NOW,
        )
        res = es.apply(cands, sqla.session)
        self.assertEqual(sorted(res["created"]), ["x-conf-org", "y-org"])
        row = sqla.session.query(db.IngestionTarget).get("x-conf-org")
        self.assertFalse(row.enabled)
        spec = ext.spec_from_target(row)
        self.assertEqual(spec.status, ext.STATUS_SUGGESTED)
        self.assertEqual(spec.found_in[0]["source"], "seed")
        self.assertEqual(ext.load_specs(sqla.session), [])
        # second run only merges
        again = es.apply(cands, sqla.session)
        self.assertEqual(again["created"], [])
        self.assertEqual(self._count(), 2)

    def test_registered_and_rejected_hosts_are_skipped(self) -> None:
        self._register("x-conf.org", ext.STATUS_REJECTED)
        self._register("approved.org", ext.STATUS_APPROVED)
        cands = es.candidates(
            [
                site(),
                site(
                    id="a",
                    url="https://approved.org/",
                    start_url="https://approved.org/p",
                ),
                site(id="n", url="https://new.org/", start_url="https://new.org/"),
            ],
            NOW,
        )
        actions = {p["id"]: p["action"] for p in es.plan(cands, sqla.session)}
        self.assertEqual(
            actions, {"x-conf-org": "skip", "approved-org": "skip", "new-org": "create"}
        )
        before = self._count()
        res = es.apply(cands, sqla.session)
        self.assertEqual(res["created"], ["new-org"])
        self.assertEqual(self._count(), before + 1)

    def test_sibling_subdomain_of_registered_host_is_allowed(self) -> None:
        self._register("2026.owaspbenelux.eu", ext.STATUS_APPROVED)
        cand = es.to_candidate(
            site(
                id="p",
                url="https://2025.owaspbenelux.eu/",
                start_url="https://2025.owaspbenelux.eu/",
            ),
            NOW,
        )
        self.assertEqual(es.plan([cand], sqla.session)[0]["action"], "create")
        same = es.to_candidate(
            site(
                id="q",
                url="https://2026.owaspbenelux.eu/",
                start_url="https://2026.owaspbenelux.eu/",
            ),
            NOW,
        )
        self.assertEqual(es.plan([same], sqla.session)[0]["action"], "skip")

    def test_limit_caps_new_rows(self) -> None:
        cands = [
            es.to_candidate(
                site(
                    id=f"s{i}", url=f"https://s{i}.org/", start_url=f"https://s{i}.org/"
                ),
                NOW,
            )
            for i in range(5)
        ]
        res = es.apply(cands, sqla.session, limit=3)
        self.assertEqual(len(res["created"]), 3)


if __name__ == "__main__":
    unittest.main()
