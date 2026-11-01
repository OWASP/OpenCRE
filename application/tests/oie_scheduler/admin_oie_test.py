import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from application import create_app, sqla
from application.utils.oie_scheduler import run_log

NOW = datetime(2026, 10, 5, 10, 7, tzinfo=timezone.utc)


def _record(job, slot, status, *, error=None, summary=None, minutes=0):
    started = NOW + timedelta(minutes=minutes)
    row = run_log.begin_run(
        sqla.session, job, slot, trigger="scheduled", dry_run=False, now=started
    )
    run_log.finish_run(
        sqla.session,
        row,
        status=status,
        summary=summary,
        error=error,
        now=started + timedelta(seconds=5),
    )
    return row.id


class AdminOieTest(unittest.TestCase):
    def setUp(self) -> None:
        env = patch.dict(
            os.environ,
            {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1", "INSECURE_REQUESTS": "True"},
        )
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_runs_list_filters_and_orders(self) -> None:
        a = _record("owasp", "20261005T1000Z", "ok", summary={"stages": []})
        b = _record("cre_expansion", "20261005T0000Z", "error", error="boom", minutes=1)
        with self.app.test_client() as c:
            body = c.get("/admin/oie/runs").get_json()
            self.assertEqual([r["id"] for r in body["runs"]], [b, a])
            only = c.get("/admin/oie/runs?job=owasp").get_json()
            self.assertEqual([r["id"] for r in only["runs"]], [a])
            failed = c.get("/admin/oie/runs?status=error").get_json()
            self.assertEqual([r["id"] for r in failed["runs"]], [b])
            self.assertEqual(failed["runs"][0]["error"], "boom")

    def test_bad_paging_arguments_are_a_400_not_a_500(self) -> None:
        with self.app.test_client() as c:
            self.assertEqual(c.get("/admin/oie/runs?limit=abc").status_code, 400)
            self.assertEqual(c.get("/admin/oie/runs?limit=99999").status_code, 200)

    def test_run_detail_and_404(self) -> None:
        rid = _record(
            "owasp",
            "20261005T1000Z",
            "ok",
            summary={"stages": [{"name": "harvest", "status": "ok", "summary": {}}]},
        )
        with self.app.test_client() as c:
            detail = c.get(f"/admin/oie/runs/{rid}").get_json()
            self.assertEqual(detail["summary"]["stages"][0]["name"], "harvest")
            self.assertEqual(detail["duration_seconds"], 5.0)
            self.assertEqual(c.get("/admin/oie/runs/nope").status_code, 404)

    def test_health_endpoint_and_strict_mode(self) -> None:
        with self.app.test_client() as c:
            body = c.get("/admin/oie/health").get_json()
            self.assertFalse(body["healthy"])
            self.assertEqual(body["jobs"]["owasp"]["state"], "never_ran")
            self.assertIn("harvest_input_pending", body["queues"])
            self.assertEqual(c.get("/admin/oie/health?strict=1").status_code, 503)

    def test_page_renders_runs_and_escapes_errors(self) -> None:
        _record(
            "owasp",
            "20261005T1000Z",
            "error",
            error="<script>alert(1)</script>",
            summary={"stages": [{"name": "harvest", "status": "error"}]},
        )
        with self.app.test_client() as c:
            resp = c.get("/admin/oie")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.content_type)
        html = resp.get_data(as_text=True)
        self.assertIn("owasp-20261005T1000Z", html)
        self.assertIn("harvest:error", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_page_with_no_runs(self) -> None:
        with self.app.test_client() as c:
            html = c.get("/admin/oie").get_data(as_text=True)
        self.assertIn("No runs recorded yet.", html)

    def test_disabled_without_import_flag(self) -> None:
        with patch.dict(os.environ, {"CRE_ALLOW_IMPORT": "0"}):
            with self.app.test_client() as c:
                for path in ("/admin/oie", "/admin/oie/runs", "/admin/oie/health"):
                    self.assertEqual(c.get(path).status_code, 404, path)


class AdminOieAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        env = patch.dict(
            os.environ, {"CRE_ALLOW_IMPORT": "1", "INSECURE_REQUESTS": "True"}
        )
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NO_LOGIN", None)
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_unauthenticated_requests_are_challenged(self) -> None:
        with self.app.test_client() as c:
            self.assertEqual(c.get("/admin/oie/runs").status_code, 401)
            self.assertEqual(c.get("/admin/oie").status_code, 401)


if __name__ == "__main__":
    unittest.main()
