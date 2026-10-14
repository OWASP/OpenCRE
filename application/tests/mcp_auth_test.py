"""Tests for OpenCRE MCP v2 authenticated tools."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application.mcp import auth, catalog, token_store
from application.mcp.openapi_loader import input_schemas_for
from application.mcp.rest_client import (
    RestClient,
    RestRequestError,
    RestResponseError,
)
from application.mcp.server import server_instructions


class _FakeResponse:
    """The three attributes rest_client reads off a response."""

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        raise ValueError("not json")


class McpAuthToolsTest(unittest.TestCase):
    def test_authenticated_tools_are_hidden_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(catalog.AUTH_TOOLS_ENV, None)
            served = catalog.active_tools()
            names = catalog.list_tool_names()
        self.assertEqual(served, catalog.PUBLIC_TOOLS)
        self.assertEqual(len(served), 9)
        self.assertNotIn("get_my_resources", names)
        with self.assertRaises(KeyError):
            catalog.get_tool("get_my_resources")

    def test_authenticated_tools_appear_when_enabled(self) -> None:
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            served = catalog.active_tools()
            names = catalog.list_tool_names()
            get_my = catalog.get_tool("get_my_resources")
        self.assertIn("get_my_resources", names)
        self.assertIn("set_my_resources", names)
        self.assertEqual(len(served), 11)
        self.assertEqual(get_my.name, "get_my_resources")

    def test_get_tool_and_list_names_respect_auth_flag(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(catalog.AUTH_TOOLS_ENV, None)
            self.assertEqual(
                catalog.list_tool_names(), [t.name for t in catalog.PUBLIC_TOOLS]
            )
            with self.assertRaises(KeyError):
                catalog.get_tool("set_my_resources")
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            self.assertIn("set_my_resources", catalog.list_tool_names())
            self.assertFalse(catalog.get_tool("set_my_resources").read_only)

    def test_server_instructions_mention_write_when_auth_tools_on(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(catalog.AUTH_TOOLS_ENV, None)
            v1 = server_instructions()
        self.assertIn("v1", v1)
        self.assertNotIn("set_my_resources", v1)
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            v2 = server_instructions()
        self.assertIn("v2", v2)
        self.assertIn("set_my_resources", v2)

    def test_no_tool_schema_can_carry_a_credential(self) -> None:
        """Credentials come from the environment, never from tool arguments."""
        forbidden = {"token", "authorization", "cookie", "bearer", "password"}
        schemas = input_schemas_for(catalog.PUBLIC_TOOLS + catalog.AUTHENTICATED_TOOLS)

        for name, schema in schemas.items():
            self.assertFalse(
                schema.get("additionalProperties", True),
                f"{name} allows unexpected arguments",
            )
            for prop in schema.get("properties") or {}:
                self.assertNotIn(prop.lower(), forbidden, f"{name}.{prop}")

    def test_write_tool_is_not_marked_read_only(self) -> None:
        """A wrong hint here makes MCP clients auto-approve writes."""
        by_name = {tool.name: tool for tool in catalog.AUTHENTICATED_TOOLS}
        self.assertTrue(by_name["get_my_resources"].read_only)
        self.assertFalse(by_name["set_my_resources"].read_only)

    def test_authenticated_tool_without_login_makes_no_http_call(self) -> None:
        class _NoHttpSession:
            cookies = None

            def request(self, *args, **kwargs):
                raise AssertionError("HTTP must not be called without a credential")

        client = RestClient(session=_NoHttpSession())
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            with patch.object(
                auth, "current_id_token", side_effect=auth.NotAuthenticated("run login")
            ):
                with self.assertRaises(RestRequestError) as ctx:
                    client.call_tool("get_my_resources", {})
        self.assertIn("run login", str(ctx.exception))

    def test_token_is_redacted_from_error_text(self) -> None:
        """Error text reaches the LLM, so it must never carry the credential."""
        token = "SECRET_ID_TOKEN_DO_NOT_LEAK"

        class _EchoSession:
            cookies = None

            def request(self, method, url, **kwargs):
                sent = kwargs["headers"]["Authorization"]
                return _FakeResponse(500, f"upstream rejected {sent}")

        client = RestClient(session=_EchoSession())
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            with patch.object(auth, "current_id_token", return_value=token):
                with self.assertRaises(RestResponseError) as ctx:
                    client.call_tool("get_my_resources", {})

        message = str(ctx.exception)
        self.assertNotIn(token, message)
        self.assertIn("<redacted>", message)

    def test_authenticated_tool_sends_a_bearer_header(self) -> None:
        token = "an-id-token"
        seen = {}

        class _CapturingSession:
            cookies = None

            def request(self, method, url, **kwargs):
                seen["method"] = method
                seen["url"] = url
                seen["headers"] = kwargs["headers"]
                return _FakeResponse(200, "[]")

        client = RestClient(session=_CapturingSession())
        with patch.dict(os.environ, {catalog.AUTH_TOOLS_ENV: "1"}):
            with patch.object(auth, "current_id_token", return_value=token):
                client.call_tool("get_my_resources", {})

        self.assertEqual(seen["method"], "GET")
        self.assertTrue(seen["url"].endswith("/rest/v1/user/resources"))
        self.assertEqual(seen["headers"]["Authorization"], f"Bearer {token}")

    def test_public_tool_sends_no_credential(self) -> None:
        seen = {}

        class _CapturingSession:
            cookies = None

            def request(self, method, url, **kwargs):
                seen["headers"] = kwargs["headers"]
                return _FakeResponse(200, "[]")

        RestClient(session=_CapturingSession()).call_tool("list_standards", {})
        self.assertNotIn("Authorization", seen["headers"])

    def test_store_requires_a_refresh_token(self) -> None:
        """Login must not succeed with only an in-memory id_token."""
        auth._cached_id_token = None
        with patch.object(token_store, "load", return_value=None):
            with patch.object(token_store, "save") as save:
                with self.assertRaises(auth.AuthError) as ctx:
                    auth._store({"id_token": "header.payload.sig"})
        self.assertIn("refresh_token", str(ctx.exception))
        save.assert_not_called()
        self.assertIsNone(auth._cached_id_token)

    def test_store_reuses_existing_refresh_token_on_refresh_response(self) -> None:
        auth._cached_id_token = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tokens.json"
            with patch.dict(os.environ, {"OPENCRE_MCP_TOKEN_FILE": str(path)}):
                token_store.save("existing-refresh")
                claims = auth._store(
                    {
                        "id_token": "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0.",
                    }
                )
        self.assertEqual(auth._cached_id_token, "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0.")
        self.assertIsInstance(claims, dict)

    def test_token_file_is_created_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tokens.json"
            with patch.dict(os.environ, {"OPENCRE_MCP_TOKEN_FILE": str(path)}):
                token_store.save("refresh-secret")
            mode = path.stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
