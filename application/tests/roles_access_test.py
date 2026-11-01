"""Two-role access: any allowed-domain account can chat and use MCP ask; only named admins can do admin things."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import mcp.types as types

from application import create_app, sqla
from application.database import db
from application.tests.mcp_remote_http_test import McpRemoteHttpTest
from application.utils.api_tokens import mint as api_mint

ROLE_ENV = {
    "ADMIN_EMAILS": "boss@owasp.org",
    "LOGIN_ALLOWED_DOMAINS": "owasp.org",
    "LOGIN_ALLOWED_EMAILS": "",
    "NO_LOGIN": "0",
    "CRE_ENABLE_LOGIN": "1",
    "INSECURE_REQUESTS": "1",
    "NO_LOAD_GRAPH_DB": "1",
    "FLASK_CONFIG": "production",
}


class WebRolesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(os.environ, ROLE_ENV)
        self._env.start()
        self.addCleanup(self._env.stop)
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _client(self, email):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = "u-" + email
            s["email"] = email
            s["google_id"] = "g-" + email
        return c

    def test_me_reports_the_role(self):
        self.assertEqual(
            self._client("boss@owasp.org").get("/rest/v1/me").get_json()["role"],
            "admin",
        )
        self.assertEqual(
            self._client("jane@owasp.org").get("/rest/v1/me").get_json()["role"], "user"
        )

    def test_account_outside_the_domain_is_refused_and_signed_out(self):
        c = self._client("eve@gmail.com")
        self.assertEqual(c.get("/rest/v1/me").status_code, 403)
        with c.session_transaction() as s:
            self.assertNotIn("user_id", s)

    def test_user_can_use_chat_endpoint_gate_but_not_admin(self):
        c = self._client("jane@owasp.org")
        handler = MagicMock()
        handler.generate_text.return_value = {"response": "ok", "accurate": True}
        with patch.dict(os.environ, {"OWASP_AGENT_ENABLED": "0"}), patch(
            "application.prompt_client.prompt_client.PromptHandler",
            return_value=handler,
        ):
            r = c.post("/rest/v1/completion", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.get_json()["response"], "ok")
        self.assertEqual(
            c.get("/rest/v1/api-keys").status_code, 403
        )  # admin-wide key list
        self.assertEqual(c.get("/admin/config").status_code, 403)
        with c.session_transaction() as s:
            self.assertIn(
                "user_id", s
            )  # a plain user is NOT signed out for poking an admin URL

    def test_chat_is_rate_limited_per_account(self):
        from application.utils import rate_limit

        rate_limit.reset_memory()
        handler = MagicMock()
        handler.generate_text.return_value = {"response": "ok", "accurate": True}
        with patch.dict(
            os.environ,
            {
                "OWASP_AGENT_ENABLED": "0",
                "RATE_LIMIT_PER_MINUTE": "2",
                "RATE_LIMIT_ENABLED": "1",
            },
        ), patch(
            "application.prompt_client.prompt_client.PromptHandler",
            return_value=handler,
        ):
            jane, bob = self._client("jane@owasp.org"), self._client("bob@owasp.org")
            codes = [
                jane.post("/rest/v1/completion", json={"prompt": "hi"}).status_code
                for _ in range(3)
            ]
            third = jane.post("/rest/v1/completion", json={"prompt": "hi"})
            other = bob.post("/rest/v1/completion", json={"prompt": "hi"}).status_code
        self.assertEqual(codes, [200, 200, 429])
        self.assertIn("Retry-After", third.headers)
        self.assertIn("per minute", third.get_json()["error"])
        self.assertEqual(other, 200)  # another account still has its own allowance

    def test_admin_passes_the_admin_gates(self):
        c = self._client("boss@owasp.org")
        self.assertEqual(c.get("/rest/v1/api-keys").status_code, 200)

    def test_user_manages_only_their_own_keys(self):
        users = db.Node_collection()
        jane = users.upsert_user(
            google_sub="g-jane@owasp.org", email="jane@owasp.org", display_name="Jane"
        )
        bob = users.upsert_user(
            google_sub="g-bob@owasp.org", email="bob@owasp.org", display_name="Bob"
        )
        bobs_key = api_mint.mint_api_token(user=bob, name="bob-key", expires_days=5)
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["user_id"], s["email"], s["google_id"], s["csrf_token"] = (
                jane.id,
                "jane@owasp.org",
                "g-jane@owasp.org",
                "tok",
            )
        hdr = {"X-CSRF-Token": "tok"}
        made = c.post("/rest/v1/my-api-keys", json={"name": "mine"}, headers=hdr)
        self.assertEqual(made.status_code, 201, made.data)
        mine = c.get("/rest/v1/my-api-keys").get_json()["keys"]
        self.assertEqual([k["name"] for k in mine], ["mine"])
        self.assertEqual(
            c.delete(f"/rest/v1/my-api-keys/{bobs_key.jti}", headers=hdr).status_code,
            404,
        )
        self.assertEqual(
            c.delete(
                f"/rest/v1/my-api-keys/{made.get_json()['jti']}", headers=hdr
            ).status_code,
            204,
        )


class McpRolesTest(unittest.TestCase):
    """Remote MCP with the two-role environment (borrows the harness helpers)."""

    _mint = McpRemoteHttpTest._mint
    _call_tool = McpRemoteHttpTest._call_tool

    def setUp(self) -> None:
        self._env = patch.dict(
            os.environ,
            {
                **ROLE_ENV,
                "API_TOKEN_JWT_SECRET": "test-api-token-jwt-secret-not-for-prod",
                "OPENCRE_MCP_REMOTE": "1",
                "OWASP_AGENT_ENABLED": "1",
            },
        )
        self._env.start()
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()
        self.boss = self.collection.upsert_user(
            google_sub="boss-sub", email="boss@owasp.org", display_name="Boss"
        )
        self.jane = self.collection.upsert_user(
            google_sub="jane-sub", email="jane@owasp.org", display_name="Jane"
        )
        self.eve = self.collection.upsert_user(
            google_sub="eve-sub", email="eve@gmail.com", display_name="Eve"
        )

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        self._env.stop()

    def _text(self, result):
        first = result.content[0]
        assert isinstance(first, types.TextContent)
        return first.text

    def test_user_may_ask_and_rate(self):
        tok = self._mint(self.jane)
        with patch("application.mcp.server.run_ask", return_value={"ok": True}) as ask:
            r = self._call_tool(
                "ask", {"prompt": "What is MFA?"}, authorization=f"Bearer {tok}"
            )
            ask.assert_called_once()
        self.assertFalse(r.is_error)

    def test_outsider_and_anonymous_are_refused(self):
        with patch("application.mcp.server.run_ask") as ask:
            eve = self._call_tool(
                "ask", {"prompt": "x"}, authorization=f"Bearer {self._mint(self.eve)}"
            )
            anon = self._call_tool("ask", {"prompt": "x"})
            ask.assert_not_called()
        self.assertTrue(eve.is_error and anon.is_error)
        self.assertRegex(self._text(eve).lower(), r"403|no access")

    def test_meta_and_source_tools_need_a_signed_in_role(self):
        self.assertTrue(
            self._call_tool("owasp_meta_sources_list", {"project": "asvs"}).is_error
        )  # anonymous
        with patch(
            "application.mcp.server.call_owasp_meta_tool", return_value={"ok": True}
        ):
            r = self._call_tool(
                "owasp_meta_sources_list",
                {"project": "asvs"},
                authorization=f"Bearer {self._mint(self.jane)}",
            )
        self.assertFalse(r.is_error, self._text(r))

    def test_public_cre_read_tools_stay_public(self):
        self.assertFalse(self._call_tool("list_standards", {}).is_error)

    def test_admin_only_tools_need_admin(self):
        from application.mcp import remote_auth

        with patch.object(remote_auth, "ADMIN_ONLY_TOOLS", frozenset({"ask"})), patch(
            "application.mcp.server.run_ask", return_value={"ok": True}
        ):
            user = self._call_tool(
                "ask", {"prompt": "x"}, authorization=f"Bearer {self._mint(self.jane)}"
            )
            admin = self._call_tool(
                "ask", {"prompt": "x"}, authorization=f"Bearer {self._mint(self.boss)}"
            )
        self.assertTrue(user.is_error)
        self.assertRegex(self._text(user).lower(), r"admin role is required")
        self.assertFalse(admin.is_error)

    def test_mcp_ask_is_rate_limited_per_account(self):
        from application.utils import rate_limit

        rate_limit.reset_memory()
        tok = self._mint(self.jane)
        with patch.dict(
            os.environ, {"RATE_LIMIT_PER_MINUTE": "2", "RATE_LIMIT_ENABLED": "1"}
        ), patch("application.mcp.server.run_ask", return_value={"ok": True}):
            results = [
                self._call_tool("ask", {"prompt": "x"}, authorization=f"Bearer {tok}")
                for _ in range(3)
            ]
        self.assertEqual([r.is_error for r in results], [False, False, True])
        self.assertTrue(self._text(results[2]).startswith("429 "))
