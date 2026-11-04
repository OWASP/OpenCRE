import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.ops import staging_host_health as h

GOOD_PS = "\n".join(
    f"opencre-staging-{n}-1|Up 2 hours"
    + (" (healthy)" if n in ("db", "redis", "neo4j") else "")
    for n in ("web", "mcp", "edge", "db", "redis", "neo4j", "worker-1", "worker-2")
)
ENV = "OWASP_CX_LONGCTX=1\nOWASP_CX_LONGCTX_CHARS=2000000\nOWASP_CX_PREFIXCACHE=1\nANSWER_LOG_ENABLED=1\nPATH=/bin\n"


def runner(ps=GOOD_PS, web_env=ENV, mcp_env=ENV, logs="", df="Use%\n 42%\n"):
    def run(cmd):
        cmd = list(cmd)
        if cmd[:2] == ["docker", "ps"]:
            return ps
        if cmd[:2] == ["docker", "exec"]:
            return web_env if "web" in cmd[2] else mcp_env
        if cmd[:2] == ["docker", "logs"]:
            return logs
        if cmd[0] == "df":
            return df
        return ""

    return run


class StagingHostHealthTest(unittest.TestCase):
    def test_healthy_staging_has_no_problems(self):
        self.assertEqual(h.collect(runner(), get=lambda u: 200), [])

    def test_missing_or_unhealthy_container_is_reported(self):
        ps = GOOD_PS.replace(
            "opencre-staging-mcp-1|Up 2 hours",
            "opencre-staging-mcp-1|Exited (1) 3 minutes ago",
        )
        self.assertIn(
            "container mcp is not running", h.collect(runner(ps=ps), get=lambda u: 200)
        )
        ps = GOOD_PS.replace("Up 2 hours (healthy)", "Up 2 hours (unhealthy)", 1)
        self.assertTrue(
            any("not healthy" in p for p in h.collect(runner(ps=ps), get=lambda u: 200))
        )

    def test_web_down_is_reported(self):
        self.assertTrue(
            any("HTTP 502" in p for p in h.collect(runner(), get=lambda u: 502))
        )

    def test_flag_drift_between_web_and_mcp_and_unexpected_flags(self):
        mcp = ENV.replace("OWASP_CX_PREFIXCACHE=1\n", "") + "OWASP_CX_ROUTE=1\n"
        problems = h.collect(runner(mcp_env=mcp), get=lambda u: 200)
        text = " | ".join(problems)
        self.assertIn("different answer settings", text)
        self.assertIn("OWASP_CX_PREFIXCACHE", text)
        self.assertIn("unexpected setting OWASP_CX_ROUTE", text)

    def test_error_burst_and_full_disk(self):
        logs = "\n".join('{"level": "ERROR", "message": "x"}' for _ in range(30))
        problems = h.collect(runner(logs=logs, df="Use%\n 95%\n"), get=lambda u: 200)
        self.assertTrue(any("logged 30 errors" in p for p in problems))
        self.assertTrue(any("95% full" in p for p in problems))

    def test_alert_dedup_cooldown_and_recovery(self):
        st = {}
        self.assertEqual(h.decide(["a"], st, now=1000, cooldown_minutes=60), "alert")
        self.assertIsNone(
            h.decide(["a"], st, now=1300, cooldown_minutes=60)
        )  # same problem, inside cooldown
        self.assertEqual(
            h.decide(["a", "b"], st, now=1400, cooldown_minutes=60), "alert"
        )  # changed
        self.assertEqual(
            h.decide(["a", "b"], st, now=1400 + 3700, cooldown_minutes=60), "alert"
        )  # reminder
        self.assertEqual(h.decide([], st, now=9000, cooldown_minutes=60), "recovered")
        self.assertIsNone(h.decide([], st, now=9300, cooldown_minutes=60))

    def test_main_sends_one_alert_then_recovery_through_notify(self):
        sent = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "scripts.ops.notify.send_alert",
            side_effect=lambda t, b, **k: sent.append(t) or [],
        ), mock.patch.object(h, "check_web", return_value=[]):
            state = os.path.join(tmp, "s.json")
            bad = runner(ps=GOOD_PS.replace("opencre-staging-edge-1|Up 2 hours", ""))
            self.assertEqual(h.main(["--notify", "--state", state], run=bad), 1)
            self.assertEqual(
                h.main(["--notify", "--state", state], run=bad), 1
            )  # cooldown: no second alert
            self.assertEqual(h.main(["--notify", "--state", state], run=runner()), 0)
        self.assertEqual(
            sent, ["OpenCRE staging needs attention", "OpenCRE staging recovered"]
        )
