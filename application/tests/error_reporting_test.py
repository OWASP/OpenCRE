import json
import os
import unittest
from unittest import mock

from flask import Flask, request

from application.utils import error_reporting as er

DSN = "https://publickey@o0.ingest.sentry.io/1"


class _Capture:
    """Stand-in transport that records the events instead of sending them."""

    def __init__(self):
        self.events = []


def _transport(capture):
    from sentry_sdk.transport import Transport

    class T(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    capture.events.append(item.payload.json)

    return T()


class ErrorReportingTest(unittest.TestCase):
    def setUp(self):
        er.reset_for_tests()
        self.addCleanup(er.reset_for_tests)

    def test_disabled_without_a_dsn(self):
        import sentry_sdk

        with mock.patch.dict(os.environ, {"SENTRY_DSN": ""}):
            self.assertFalse(er.init_error_reporting("web"))
        self.assertFalse(sentry_sdk.get_client().dsn)  # nothing could be sent anywhere

    def test_an_unhandled_error_is_reported_without_personal_data(self):
        import sentry_sdk

        cap = _Capture()
        app = Flask(__name__)

        @app.route("/boom", methods=["POST"])
        def boom():
            raise RuntimeError("lookup failed for jane@owasp.org")

        with mock.patch.dict(
            os.environ,
            {
                "SENTRY_DSN": DSN,
                "SENTRY_ENVIRONMENT": "staging",
                "SENTRY_RELEASE": "abc123",
            },
        ):
            self.assertTrue(er.init_error_reporting("web", transport=_transport(cap)))
            sentry_sdk.set_user({"email": "jane@owasp.org", "id": "42"})
            app.testing = False
            client = app.test_client()
            client.post(
                "/boom",
                json={
                    "prompt": "how do I secret-handshake with the admin panel?",
                    "messages": [{"content": "private"}],
                },
                headers={
                    "Authorization": "Bearer SECRETTOKEN",
                    "Cookie": "session=abc",
                },
            )
            sentry_sdk.flush()
        self.assertEqual(len(cap.events), 1)
        event = cap.events[0]
        blob = json.dumps(event)
        for leaked in (
            "secret-handshake",
            "private",
            "SECRETTOKEN",
            "session=abc",
            "jane@owasp.org",
        ):
            self.assertNotIn(leaked, blob, leaked)
        self.assertEqual(event["environment"], "staging")
        self.assertEqual(event["release"], "abc123")
        self.assertEqual(event["tags"]["component"], "web")
        self.assertIn("RuntimeError", blob)
        self.assertNotIn("user", event)

    def test_scrub_event_removes_local_variables_and_request_data(self):
        event = {
            "request": {
                "data": {"prompt": "x"},
                "headers": {"Authorization": "t", "Accept": "json"},
                "cookies": {"a": "b"},
            },
            "user": {"email": "a@b.org"},
            "exception": {
                "values": [
                    {
                        "value": "bad for a@b.org",
                        "stacktrace": {"frames": [{"vars": {"prompt": "p"}}]},
                    }
                ]
            },
        }
        out = er.scrub_event(event)
        self.assertNotIn("data", out["request"])
        self.assertEqual(out["request"]["headers"]["Authorization"], "[removed]")
        self.assertEqual(out["request"]["headers"]["Accept"], "json")
        self.assertNotIn("user", out)
        self.assertEqual(out["exception"]["values"][0]["value"], "bad for [email]")
        self.assertNotIn(
            "vars", out["exception"]["values"][0]["stacktrace"]["frames"][0]
        )
