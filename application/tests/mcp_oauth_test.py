"""Remote MCP Google sign-in: the OAuth endpoints, the allowlist, and token issue/refresh."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import unittest
from typing import Any, Dict, Optional, Tuple
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient

from application import create_app, sqla
from application.mcp import oauth
from application.mcp.http_app import create_http_app

REDIRECT = "http://localhost:9999/cb"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def claims(email: str, verified: bool = True) -> Dict[str, Any]:
    return {
        "sub": "sub-" + email,
        "email": email,
        "email_verified": verified,
        "name": "T",
    }


class McpOAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(
            os.environ,
            {
                "NO_LOAD_GRAPH_DB": "1",
                "API_TOKEN_JWT_SECRET": "test-api-token-jwt-secret-not-for-prod",
                "INSECURE_REQUESTS": "1",
                "CRE_ENABLE_LOGIN": "1",
                "FLASK_CONFIG": "production",
                "OPENCRE_MCP_REMOTE": "1",
                "OPENCRE_MCP_OAUTH": "1",
                "OPENCRE_MCP_PUBLIC_URL": "https://testserver",
                "OPENCRE_MCP_ALLOWED_DOMAINS": "owasp.org",
                "LOGIN_ALLOWED_DOMAINS": "owasp.org",
                "ADMIN_EMAILS": "boss@owasp.org",
                "GOOGLE_CLIENT_ID": "gid",
                "GOOGLE_CLIENT_SECRET": "gsecret",
            },
        )
        self._env.start()
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.client_cm = TestClient(
            create_http_app(allowed_hosts=["testserver"]),
            base_url="https://testserver",
            follow_redirects=False,
        )
        self.http = self.client_cm.__enter__()

    def tearDown(self) -> None:
        self.client_cm.__exit__(None, None, None)
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()
        self._env.stop()

    # --- helpers -------------------------------------------------------------------------

    def _register(self) -> str:
        res = self.http.post(
            "/register",
            json={
                "redirect_uris": [REDIRECT],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_name": "test",
            },
        )
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["client_id"]

    def _sign_in(
        self, client_id: str, google_claims: Dict[str, Any]
    ) -> Tuple[str, Dict[str, list]]:
        """Run /authorize and the Google callback; returns (code_verifier, redirect query)."""
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        res = self.http.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "client-state",
                "resource": "https://testserver/mcp",
            },
        )
        self.assertEqual(res.status_code, 302, res.text)
        google = urlparse(res.headers["location"])
        self.assertEqual(google.netloc, "accounts.google.com")
        gq = parse_qs(google.query)
        self.assertEqual(
            gq["redirect_uri"], ["https://testserver/oauth/google/callback"]
        )
        self.assertEqual(gq["hd"], ["owasp.org"])
        with patch.object(
            oauth.OpenCREOAuthProvider, "_google_claims", return_value=google_claims
        ):
            back = self.http.get(
                "/oauth/google/callback",
                params={"code": "google-code", "state": gq["state"][0]},
            )
        self.assertEqual(back.status_code, 302, back.text)
        location = urlparse(back.headers["location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}", REDIRECT
        )
        return verifier, parse_qs(location.query)

    def _token(self, client_id: str, **form: str) -> Any:
        return self.http.post("/token", data={"client_id": client_id, **form})

    def _exchange(
        self, client_id: str, email: str = "alice@owasp.org"
    ) -> Dict[str, Any]:
        verifier, q = self._sign_in(client_id, claims(email))
        self.assertEqual(q["state"], ["client-state"])
        res = self._token(
            client_id,
            grant_type="authorization_code",
            code=q["code"][0],
            redirect_uri=REDIRECT,
            code_verifier=verifier,
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    # --- tests ---------------------------------------------------------------------------

    def test_discovery_and_unauthenticated_challenge(self) -> None:
        meta = self.http.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(meta["authorization_endpoint"], "https://testserver/authorize")
        self.assertEqual(meta["registration_endpoint"], "https://testserver/register")
        resource = self.http.get("/.well-known/oauth-protected-resource/mcp").json()
        self.assertEqual(resource["resource"], "https://testserver/mcp")
        res = self.http.post("/mcp", json=INIT, headers=MCP_HEADERS)
        self.assertEqual(res.status_code, 401)
        self.assertIn("resource_metadata", res.headers["www-authenticate"])

    def test_full_sign_in_issues_a_token_that_opens_the_mcp_endpoint(self) -> None:
        tokens = self._exchange(self._register())
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertTrue(tokens["refresh_token"])
        res = self.http.post(
            "/mcp",
            json=INIT,
            headers={
                **MCP_HEADERS,
                "Authorization": "Bearer " + tokens["access_token"],
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_code_is_single_use_and_needs_the_pkce_verifier(self) -> None:
        client_id = self._register()
        verifier, q = self._sign_in(client_id, claims("alice@owasp.org"))
        form = dict(
            grant_type="authorization_code",
            code=q["code"][0],
            redirect_uri=REDIRECT,
        )
        bad = self._token(client_id, code_verifier="wrong" * 10, **form)
        self.assertEqual(bad.status_code, 400)
        ok = self._token(client_id, code_verifier=verifier, **form)
        self.assertEqual(ok.status_code, 200, ok.text)
        again = self._token(client_id, code_verifier=verifier, **form)
        self.assertEqual(again.status_code, 400)

    def test_account_outside_the_allowed_domains_gets_no_code(self) -> None:
        client_id = self._register()
        _, q = self._sign_in(client_id, claims("mallory@gmail.com"))
        self.assertEqual(q["error"], ["access_denied"])
        self.assertNotIn("code", q)
        self.assertEqual(q["state"], ["client-state"])

    def test_unverified_email_gets_no_code(self) -> None:
        _, q = self._sign_in(
            self._register(), claims("alice@owasp.org", verified=False)
        )
        self.assertEqual(q["error"], ["access_denied"])

    def test_refresh_rotates_and_the_old_refresh_token_dies(self) -> None:
        client_id = self._register()
        first = self._exchange(client_id)
        res = self._token(
            client_id, grant_type="refresh_token", refresh_token=first["refresh_token"]
        )
        self.assertEqual(res.status_code, 200, res.text)
        second = res.json()
        self.assertNotEqual(second["refresh_token"], first["refresh_token"])
        reuse = self._token(
            client_id, grant_type="refresh_token", refresh_token=first["refresh_token"]
        )
        self.assertEqual(reuse.status_code, 400)

    def test_refresh_is_refused_once_the_account_loses_access(self) -> None:
        client_id = self._register()
        first = self._exchange(client_id)
        with patch.dict(
            os.environ,
            {
                "LOGIN_ALLOWED_DOMAINS": "example.com",
                "OPENCRE_MCP_ALLOWED_DOMAINS": "example.com",
            },
        ):
            res = self._token(
                client_id,
                grant_type="refresh_token",
                refresh_token=first["refresh_token"],
            )
        self.assertEqual(res.status_code, 400)

    def test_revoked_access_token_stops_working(self) -> None:
        client_id = self._register()
        tokens = self._exchange(client_id)
        res = self.http.post(
            "/revoke",
            data={
                "client_id": client_id,
                "client_secret": "",  # the SDK requires the field to be present
                "token": tokens["access_token"],
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        res = self.http.post(
            "/mcp",
            json=INIT,
            headers={
                **MCP_HEADERS,
                "Authorization": "Bearer " + tokens["access_token"],
            },
        )
        self.assertEqual(res.status_code, 401)

    def test_expired_sign_in_link_is_rejected(self) -> None:
        res = self.http.get(
            "/oauth/google/callback", params={"code": "x", "state": "nope"}
        )
        self.assertEqual(res.status_code, 400)


class AllowedDomainsTest(unittest.TestCase):
    def _env(self, **env: str) -> Any:
        return patch.dict(
            os.environ,
            {"OPENCRE_MCP_ALLOWED_DOMAINS": "", "LOGIN_ALLOWED_DOMAINS": "", **env},
        )

    def test_dedicated_setting_wins_over_the_login_setting(self) -> None:
        with self._env(
            OPENCRE_MCP_ALLOWED_DOMAINS="owasp.org", LOGIN_ALLOWED_DOMAINS="*"
        ):
            self.assertTrue(oauth.domain_allowed("a@owasp.org"))
            self.assertFalse(oauth.domain_allowed("a@gmail.com"))

    def test_falls_back_to_login_domains(self) -> None:
        with self._env(LOGIN_ALLOWED_DOMAINS="owasp.org, @example.com"):
            self.assertTrue(oauth.domain_allowed("a@example.com"))
            self.assertTrue(oauth.domain_allowed("a@chapters.owasp.org"))
            self.assertFalse(oauth.domain_allowed("a@notowasp.org"))

    def test_empty_fails_closed_and_star_allows_any(self) -> None:
        with self._env():
            self.assertFalse(oauth.domain_allowed("a@owasp.org"))
        with self._env(OPENCRE_MCP_ALLOWED_DOMAINS="*"):
            self.assertTrue(oauth.domain_allowed("a@anywhere.io"))


if __name__ == "__main__":
    unittest.main()
