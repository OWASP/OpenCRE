"""Tests for scripts/monitor_chatbot_health.py and chatbot sanitize guardrail."""

import io
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from scripts import monitor_chatbot_health as monitor

REPO_ROOT = Path(__file__).resolve().parents[2]
CHATBOT_TSX = REPO_ROOT / "application/frontend/src/pages/chatbot/chatbot.tsx"


class ChatbotSanitizeGuardrailTest(unittest.TestCase):
    def test_chatbot_uses_dompurify_method_not_named_sanitize_import(self) -> None:
        src = CHATBOT_TSX.read_text(encoding="utf-8")
        self.assertNotIn("import DOMPurify, { sanitize }", src)
        self.assertNotIn("{ sanitize } from 'dompurify'", src)
        self.assertIn("DOMPurify.sanitize", src)
        self.assertIn("renderChatMarkdown", src)


class AnalyzeBundleJsTest(unittest.TestCase):
    def test_flags_webpack_named_sanitize_interop(self) -> None:
        broken = (
            "dangerouslySetInnerHTML:{__html:(0,e.sanitize)(dx(t),"
            "{USE_PROFILES:{html:!0}})}"
        )
        result = monitor.analyze_bundle_js(broken)
        self.assertFalse(result["ok"])
        self.assertEqual(result["bucket"], "broken_named_sanitize_interop")

    def test_requires_two_dompurify_sanitize_string_calls(self) -> None:
        only_one = "Fw.sanitize(String(t),{USE_PROFILES:{html:!0}})"
        result = monitor.analyze_bundle_js(only_one)
        self.assertFalse(result["ok"])
        self.assertEqual(result["bucket"], "missing_dompurify_sanitize_string")

    def test_healthy_bundle_pattern_passes(self) -> None:
        healthy = (
            "return Fw.sanitize(String(t),{USE_PROFILES:{html:!0}})}"
            "const n=Fw.sanitize(String(t),{USE_PROFILES:{html:!0}});"
        )
        result = monitor.analyze_bundle_js(healthy)
        self.assertTrue(result["ok"])
        self.assertEqual(result["bucket"], "ok")
        self.assertEqual(result["healthy_sanitize_string_hits"], 2)


class MonitorChatbotHealthTest(unittest.TestCase):
    def test_chatbot_page_ok_when_bundle_referenced(self) -> None:
        html = b"<!doctype html><script src='/bundle.js'></script>"

        with mock.patch("urllib.request.urlopen") as urlopen:
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = html
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            urlopen.return_value = resp
            result = monitor.check_chatbot_page("https://opencre.org", 10)

        self.assertTrue(result["ok"])
        self.assertEqual(result["bucket"], "ok")

    def test_chatbot_page_fails_without_bundle(self) -> None:
        html = b"<!doctype html><title>oops</title>"

        with mock.patch("urllib.request.urlopen") as urlopen:
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = html
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            urlopen.return_value = resp
            result = monitor.check_chatbot_page("https://opencre.org", 10)

        self.assertFalse(result["ok"])
        self.assertEqual(result["bucket"], "missing_bundle_js")

    def test_completion_unauthenticated_expects_401(self) -> None:
        err = urllib.error.HTTPError(
            "https://opencre.org/rest/v1/completion",
            401,
            "Unauthorized",
            None,
            io.BytesIO(b"login required"),
        )
        with mock.patch("urllib.request.urlopen", side_effect=err):
            result = monitor.check_completion_unauthenticated("https://opencre.org", 10)

        self.assertTrue(result["ok"])
        self.assertEqual(result["bucket"], "ok_401")
        self.assertEqual(result["status_code"], 401)

    def test_completion_unauthenticated_fails_on_503(self) -> None:
        err = urllib.error.HTTPError(
            "https://opencre.org/rest/v1/completion",
            503,
            "Service Unavailable",
            None,
            io.BytesIO(b"unavailable"),
        )
        with mock.patch("urllib.request.urlopen", side_effect=err):
            result = monitor.check_completion_unauthenticated("https://opencre.org", 10)

        self.assertFalse(result["ok"])
        self.assertEqual(result["bucket"], "unexpected_http_503")


if __name__ == "__main__":
    unittest.main()
