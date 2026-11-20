"""Network failure handling for the MCP Google device flow."""

import os
import unittest
from unittest.mock import patch

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

    def test_login_reports_poll_timeout(self) -> None:
        class DeviceResponse:
            status_code = 200

            def json(self):
                return {
                    "verification_url": "https://example.invalid/verify",
                    "user_code": "CODE",
                    "interval": 0,
                    "expires_in": 60,
                    "device_code": "device-code",
                }

        with patch.object(
            auth.requests,
            "post",
            side_effect=[DeviceResponse(), requests.Timeout("secret")],
        ):
            with patch.object(auth.time, "sleep"):
                with self.assertRaisesRegex(
                    auth.AuthError, "device authorization polling timed out after 30s"
                ) as error:
                    auth.login(lambda url, code: None)
        self.assertNotIn("secret", str(error.exception))

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
