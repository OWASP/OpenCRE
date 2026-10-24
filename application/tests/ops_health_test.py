import http.server
import json
import os
import threading
import unittest
from unittest import mock

from scripts.ops import health_check, notify


class _Handler(http.server.BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802
        status, body = self.routes.get(self.path, (404, ""))
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):  # noqa: N802
        self.server.posts.append(
            (
                self.path,
                self.rfile.read(int(self.headers.get("Content-Length", 0))),
                dict(self.headers),
            )
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


class HealthCheckTest(unittest.TestCase):
    def setUp(self):
        _Handler.routes = {
            "/": (200, "<html>"),
            "/rest/v1/standards": (200, json.dumps({"standards": ["ASVS", "SAMM"]})),
            "/rest/v1/ga_standards": (200, json.dumps(["ASVS"])),
        }
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.server.posts = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_healthy_site_passes(self):
        results = health_check.run_checks(self.base)
        self.assertTrue(all(r["ok"] for r in results), results)
        self.assertEqual(health_check.main(["--base-url", self.base]), 0)

    def test_empty_api_list_or_http_error_fails(self):
        _Handler.routes["/rest/v1/ga_standards"] = (200, "[]")
        self.assertEqual(health_check.main(["--base-url", self.base]), 1)
        _Handler.routes["/rest/v1/ga_standards"] = (503, "")
        self.assertEqual(health_check.main(["--base-url", self.base]), 1)

    def test_unreachable_site_fails(self):
        self.assertEqual(health_check.main(["--base-url", "http://127.0.0.1:9"]), 1)

    def test_slow_response_counts_as_failure(self):
        def slow(url):
            return 200, "[1]", health_check.SLOW_SECONDS + 1

        self.assertFalse(
            all(r["ok"] for r in health_check.run_checks(self.base, get=slow))
        )

    def test_failure_alerts_webhook_and_ntfy_but_success_does_not(self):
        env = {
            "ALERT_WEBHOOK_URL": self.base + "/hook",
            "NTFY_URL": self.base + "/topic",
        }
        with mock.patch.dict(os.environ, env):
            health_check.main(["--base-url", self.base, "--notify"])
            self.assertEqual(self.server.posts, [])  # healthy: silent
            _Handler.routes["/"] = (500, "")
            health_check.main(["--base-url", self.base, "--notify"])
        paths = [p[0] for p in self.server.posts]
        self.assertEqual(sorted(paths), ["/hook", "/topic"])
        hook = json.loads([p for p in self.server.posts if p[0] == "/hook"][0][1])
        self.assertIn("home page answers", hook["text"])

    def test_notify_without_configuration_is_a_noop(self):
        with mock.patch.dict(os.environ, {"ALERT_WEBHOOK_URL": "", "NTFY_URL": ""}):
            self.assertEqual(notify.send_alert("t", "b"), [])

    def test_notify_never_raises_on_a_dead_endpoint(self):
        with mock.patch.dict(os.environ, {"ALERT_WEBHOOK_URL": "http://127.0.0.1:9/x"}):
            self.assertEqual(notify.send_alert("t", "b", timeout=0.5), [])


class UptimeMonitorSyncTest(unittest.TestCase):
    def _cfg(self, tmp):
        import tempfile  # noqa: F401

        path = os.path.join(tmp, "m.json")
        json.dump(
            {
                "interval_seconds": 300,
                "monitors": [
                    {"name": "a", "url": "https://x.org/", "type": "http"},
                    {
                        "name": "b",
                        "url": "https://x.org/api",
                        "type": "keyword",
                        "keyword": "ok",
                    },
                ],
            },
            open(path, "w"),
        )
        return path

    def test_dry_run_without_a_key_never_calls_the_network(self):
        import tempfile
        from scripts.ops import sync_uptime_monitors as s

        called = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"UPTIMEROBOT_API_KEY": ""}
        ):
            self.assertEqual(
                s.main(
                    ["--config", self._cfg(tmp)], post=lambda *a: called.append(a) or {}
                ),
                0,
            )
        self.assertEqual(called, [])

    def test_only_missing_monitors_are_created_and_contacts_are_attached(self):
        import tempfile
        from scripts.ops import sync_uptime_monitors as s

        sent = []

        def post(endpoint, fields):
            sent.append((endpoint, fields))
            return (
                {"stat": "ok", "monitors": [{"url": "https://x.org"}]}
                if endpoint == "getMonitors"
                else {"stat": "ok"}
            )

        env = {"UPTIMEROBOT_API_KEY": "k", "UPTIMEROBOT_ALERT_CONTACTS": "123_0_0"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env):
            s.main(["--config", self._cfg(tmp), "--apply"], post=post)
            created = [f for e, f in sent if e == "newMonitor"]
            self.assertEqual(
                [c["friendly_name"] for c in created], ["b"]
            )  # "a" matched by URL (trailing slash ignored)
            self.assertEqual(created[0]["alert_contacts"], "123_0_0")
            self.assertEqual(created[0]["keyword_value"], "ok")
            sent.clear()
            s.main(
                ["--config", self._cfg(tmp)], post=post
            )  # without --apply: nothing is created
            self.assertEqual([e for e, _ in sent], ["getMonitors"])
