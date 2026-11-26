"""Network failure handling for the MCP Google device flow."""

import os
import unittest
from unittest.mock import Mock, call, patch

import requests

from application.mcp import auth, cli, token_store


class McpAuthNetworkTest(unittest.TestCase):
    def setUp(self) -> None:
        auth._cached_id_token = None
        self.credentials = patch.dict(
            os.environ,
            {"GOOGLE_MCP_CLIENT_ID": "client", "GOOGLE_MCP_CLIENT_SECRET": "secret"},
        )
        self.credentials.start()
        self.addCleanup(self.credentials.stop)

    def test_login_reports_device_endpoint_connection_failure(self) -> None:
        with patch.object(
            auth.requests, "post", side_effect=requests.ConnectionError("secret")
        ):
            with patch.object(cli, "_say") as say:
                self.assertEqual(cli._login(), 1)
        say.assert_called_once_with(
            "Login failed: device authorization could not reach Google"
        )

    def test_login_retries_poll_timeouts_with_backoff(self) -> None:
        class DeviceResponse:
            status_code = 200

            def json(self):
                return {
                    "verification_url": "https://example.invalid/verify",
                    "user_code": "CODE",
                    "interval": 5,
                    "expires_in": 60,
                    "device_code": "device-code",
                }

        with patch.object(
            auth.requests,
            "post",
            side_effect=[
                DeviceResponse(),
                requests.ConnectTimeout("secret"),
                requests.ConnectTimeout("secret"),
                Mock(status_code=200, json=lambda: {"refresh_token": "refresh"}),
            ],
        ):
            with patch.object(auth.time, "sleep") as sleep:
                with patch.object(token_store, "save") as save:
                    auth.login(lambda url, code: None)
        self.assertEqual(sleep.call_args_list, [call(5), call(10), call(20)])
        save.assert_called_once_with("refresh")

    def test_poll_timeout_stops_when_code_expires(self) -> None:
        device = Mock(status_code=200)
        device.json.return_value = {
            "verification_url": "https://example.invalid/verify",
            "user_code": "CODE",
            "interval": 5,
            "expires_in": 60,
            "device_code": "device-code",
        }
        with patch.object(
            auth.requests,
            "post",
            side_effect=[device] + [requests.ConnectTimeout("secret")] * 3,
        ) as post:
            with patch.object(auth.time, "time", return_value=0) as clock:

                def advance(seconds):
                    clock.return_value += seconds

                with patch.object(auth.time, "sleep", side_effect=advance) as sleep:
                    with self.assertRaisesRegex(auth.AuthError, "code expired"):
                        auth.login(lambda url, code: None)
        self.assertEqual(post.call_count, 4)
        self.assertEqual(sleep.call_args_list, [call(5), call(10), call(20), call(25)])
        self.assertEqual(clock.return_value, 60)

    def test_status_reports_refresh_connection_failure(self) -> None:
        with patch.object(token_store, "load", return_value="stored-refresh-token"):
            with patch.object(
                auth.requests, "post", side_effect=requests.ConnectionError("secret")
            ):
                info = auth.status()
        self.assertFalse(info["logged_in"])
        self.assertEqual(info["error"], "token refresh could not reach Google")
        self.assertNotIn("secret", str(info))

    def test_refresh_keeps_transport_timeout_distinct(self) -> None:
        with patch.object(
            auth.requests, "post", side_effect=requests.Timeout("secret")
        ):
            with self.assertRaisesRegex(
                auth.AuthError, "token refresh timed out after 30s"
            ):
                auth._refresh("stored-refresh-token")


if __name__ == "__main__":
    unittest.main()
