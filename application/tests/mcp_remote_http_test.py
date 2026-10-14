"""Remote Streamable HTTP MCP: staging flag + Admin JWT gate for ask only."""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from application import create_app, sqla
from application.database import db
from application.mcp.server import ASK_TOOL_NAME, build_server
from application.utils.api_tokens import mint as api_mint

import mcp.types as types


class McpRemoteHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_no_load_graph = os.environ.get("NO_LOAD_GRAPH_DB")
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self._env = patch.dict(
            os.environ,
            {
                "API_TOKEN_JWT_SECRET": "test-api-token-jwt-secret-not-for-prod",
                "INSECURE_REQUESTS": "1",
                "CRE_ENABLE_LOGIN": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "LOGIN_ALLOWED_EMAILS": "admin@example.com",
                "FLASK_CONFIG": "production",
                "OPENCRE_MCP_REMOTE": "1",
            },
            clear=False,
        )
        self._env.start()
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.admin = self.collection.upsert_user(
            google_sub="admin-sub",
            email="admin@example.com",
            display_name="Admin",
        )
        self.outsider = self.collection.upsert_user(
            google_sub="out-sub",
            email="outsider@example.com",
            display_name="Out",
        )

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        self._env.stop()
        if self._prev_no_load_graph is None:
            os.environ.pop("NO_LOAD_GRAPH_DB", None)
        else:
            os.environ["NO_LOAD_GRAPH_DB"] = self._prev_no_load_graph

    def _mint(self, user: db.User, name: str = "mcp") -> str:
        return api_mint.mint_api_token(user=user, name=name, expires_days=30).token

    def _call_tool(
        self,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
        *,
        authorization: Optional[str] = None,
        rest_client: Any = None,
    ) -> types.CallToolResult:
        from application.mcp import remote_auth

        client = rest_client or MagicMock()
        if rest_client is None:
            client.call_tool.return_value = MagicMock(
                data={"ok": True, "standards": []},
            )
        server = build_server(rest_client=client)
        call_handler = server.get_request_handler("tools/call")
        assert call_handler is not None

        async def _run() -> types.CallToolResult:
            token = remote_auth.authorization_header.set(authorization)
            try:
                result = await call_handler.handler(
                    None,
                    types.CallToolRequestParams(
                        name=tool_name, arguments=arguments or {}
                    ),
                )
            finally:
                remote_auth.authorization_header.reset(token)
            assert isinstance(result, types.CallToolResult)
            return result

        return asyncio.run(_run())

    def test_serve_http_refuses_without_remote_flag(self) -> None:
        from application.mcp import cli

        with patch.dict(os.environ, {"OPENCRE_MCP_REMOTE": ""}, clear=False):
            os.environ.pop("OPENCRE_MCP_REMOTE", None)
            code = cli.parse_and_run_command(["serve-http"])
        self.assertNotEqual(code, 0)

    def test_public_tool_ok_without_bearer(self) -> None:
        result = self._call_tool("list_standards", {})
        self.assertFalse(result.is_error)
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        self.assertIn("standards", json.loads(first.text))

    def test_ask_without_bearer_is_denied(self) -> None:
        with patch("application.mcp.server.run_ask") as ask_mock:
            result = self._call_tool(
                ASK_TOOL_NAME, {"prompt": "What is MFA?", "corpus": "security"}
            )
            ask_mock.assert_not_called()
        self.assertTrue(result.is_error)
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        self.assertRegex(first.text.lower(), r"401|unauthorized|bearer|auth")

    def test_ask_with_allowlisted_jwt_succeeds(self) -> None:
        token = self._mint(self.admin)
        with patch(
            "application.mcp.server.run_ask",
            return_value={"ok": True, "channel": "security", "items": []},
        ) as ask_mock:
            result = self._call_tool(
                ASK_TOOL_NAME,
                {"prompt": "What is MFA?", "corpus": "security"},
                authorization=f"Bearer {token}",
            )
            ask_mock.assert_called_once()
        self.assertFalse(result.is_error)
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        payload = json.loads(first.text)
        self.assertTrue(payload["ok"])

    def test_ask_with_non_allowlisted_jwt_denied(self) -> None:
        token = self._mint(self.outsider)
        with patch("application.mcp.server.run_ask") as ask_mock:
            result = self._call_tool(
                ASK_TOOL_NAME,
                {"prompt": "What is MFA?", "corpus": "security"},
                authorization=f"Bearer {token}",
            )
            ask_mock.assert_not_called()
        self.assertTrue(result.is_error)
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        self.assertRegex(first.text.lower(), r"403|allowlist|forbidden")

    def test_ask_with_revoked_jwt_denied(self) -> None:
        minted = api_mint.mint_api_token(
            user=self.admin, name="revoked", expires_days=30
        )
        self.assertTrue(api_mint.revoke_api_token(minted.jti))
        with patch("application.mcp.server.run_ask") as ask_mock:
            result = self._call_tool(
                ASK_TOOL_NAME,
                {"prompt": "What is MFA?", "corpus": "security"},
                authorization=f"Bearer {minted.token}",
            )
            ask_mock.assert_not_called()
        self.assertTrue(result.is_error)

    def test_stdio_path_ask_ungated_when_remote_flag_off(self) -> None:
        with patch.dict(os.environ, {"OPENCRE_MCP_REMOTE": "0"}, clear=False):
            with patch(
                "application.mcp.server.run_ask",
                return_value={"ok": True, "channel": "security", "items": []},
            ) as ask_mock:
                result = self._call_tool(
                    ASK_TOOL_NAME,
                    {"prompt": "What is MFA?", "corpus": "security"},
                )
                ask_mock.assert_called_once()
        self.assertFalse(result.is_error)

    def test_host_allowlist_rejects_wrong_host(self) -> None:
        from starlette.testclient import TestClient

        from application.mcp.http_app import create_http_app

        with patch.dict(
            os.environ,
            {
                "OPENCRE_MCP_REMOTE": "1",
                "OPENCRE_MCP_ALLOWED_HOSTS": "staging.opencre.org",
            },
            clear=False,
        ):
            app = create_http_app()
            # Lifespan starts StreamableHTTPSessionManager task group.
            with TestClient(app) as client:
                resp = client.get("/mcp", headers={"Host": "evil.example"})
        self.assertEqual(resp.status_code, 421)

    def test_verify_admin_allowlisted_helper_is_path_agnostic(self) -> None:
        from application.utils.api_tokens import verify as api_verify

        token = self._mint(self.admin)
        identity = api_verify.verify_admin_allowlisted_api_token(token)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.email, "admin@example.com")

        bad = api_verify.verify_admin_allowlisted_api_token(self._mint(self.outsider))
        self.assertIsNone(bad)

        with patch.dict(
            os.environ,
            {"LOGIN_ALLOWED_EMAILS": "", "FLASK_CONFIG": "production"},
            clear=False,
        ):
            self.assertIsNone(api_verify.verify_admin_allowlisted_api_token(token))


if __name__ == "__main__":
    unittest.main()
