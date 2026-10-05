import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from application import create_app, sqla
from application.utils.oie_scheduler import run_log
from scripts import monitor_oie_health as monitor


class MonitorOieHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _check(self, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = monitor.check(sqla.session, **kw)
        return code, buf.getvalue()

    def test_fresh_database_is_unhealthy(self) -> None:
        code, out = self._check()
        self.assertEqual(code, 1)
        self.assertIn("ATTENTION", out)
        self.assertIn("never_ran", out)

    def test_healthy_when_every_job_succeeded_recently(self) -> None:
        now = datetime.now(timezone.utc)
        for job in ("owasp", "cre_expansion"):
            slot = run_log.slot_for(1, now)
            row = run_log.begin_run(
                sqla.session, job, slot, trigger="scheduled", dry_run=False, now=now
            )
            run_log.finish_run(
                sqla.session, row, status="ok", summary={}, error=None, now=now
            )
        code, out = self._check()
        self.assertEqual(code, 0)
        self.assertIn("healthy", out)

    def test_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "health.json"
            self._check(output_json=str(target))
            report = json.loads(target.read_text())
        self.assertIn("jobs", report)
        self.assertIn("queues", report)

    def test_missing_database_url_is_exit_2(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"CRE_CACHE_FILE": ""}):
            self.assertEqual(monitor.main([]), 2)


if __name__ == "__main__":
    unittest.main()
