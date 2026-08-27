"""Tests for the /rest/v1/auth/* migration (issue #963, RFC #876 TODO 1).

Canonical auth routes, deprecated aliases (header-only), login_required content
negotiation (browser 302 vs JSON 401), the user_id-keyed session predicate, and
the NO_LOGIN dev bypass. OpenAPI documentation is intentionally out of scope here.
"""

import os
import unittest
import urllib.parse
from typing import Any
from unittest.mock import patch

from application import create_app, sqla
from application.database import db


class TestAuthRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_no_load_graph = os.environ.get("NO_LOAD_GRAPH_DB")
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        if self._prev_no_load_graph is None:
            os.environ.pop("NO_LOAD_GRAPH_DB", None)
        else:
            os.environ["NO_LOAD_GRAPH_DB"] = self._prev_no_load_graph

    # --- canonical routes ---
    def test_auth_logout_clears_session_and_redirects(self) -> None:
        with patch.dict(os.environ, {"INSECURE_REQUESTS": "1"}):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "uid"
                resp = client.get("/rest/v1/auth/logout")
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp.headers["Location"].endswith("/"))
                with client.session_transaction() as sess:
                    self.assertNotIn("user_id", sess)

    def test_auth_login_dev_bypass_sets_session(self) -> None:
        with patch.dict(
            os.environ,
            {"NO_LOGIN": "1", "CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"},
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/auth/login")
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp.headers["Location"].endswith("/chatbot"))
                with client.session_transaction() as sess:
                    self.assertIn("user_id", sess)

    def test_auth_user_returns_email_when_logged_in(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "uid"
                    sess["email"] = "e@x.com"
                resp = client.get(
                    "/rest/v1/auth/user", headers={"Accept": "application/json"}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.data.decode(), "e@x.com")

    @patch("application.web.web_main.id_token")
    @patch("application.web.web_main.CREFlow")
    def test_auth_callback_sets_user_id(
        self, cre_flow_mock: Any, id_token_mock: Any
    ) -> None:
        id_token_mock.verify_oauth2_token.return_value = {
            "sub": "sub-xyz",
            "name": "Test User",
            "email": "test@example.com",
        }
        cre_flow_mock.instance.return_value.flow.credentials._id_token = "tok"
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["state"] = "xyz"
                client.get("/rest/v1/auth/callback?state=xyz")
                with client.session_transaction() as sess:
                    self.assertIn("user_id", sess)
        self.assertEqual(sqla.session.query(db.User).count(), 1)

    # --- deprecated aliases: header-only ---
    def test_logout_alias_carries_deprecation_header(self) -> None:
        with patch.dict(os.environ, {"INSECURE_REQUESTS": "1"}):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/logout")
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(resp.headers.get("Deprecation"), "true")
                self.assertIn("/rest/v1/auth/logout", resp.headers.get("Link", ""))
                self.assertIn("successor-version", resp.headers.get("Link", ""))

    def test_user_alias_carries_deprecation_header(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "uid"
                    sess["email"] = "e@x.com"
                resp = client.get(
                    "/rest/v1/user", headers={"Accept": "application/json"}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.headers.get("Deprecation"), "true")
                self.assertIn("/rest/v1/auth/user", resp.headers.get("Link", ""))

    @patch("application.web.web_main.id_token")
    @patch("application.web.web_main.CREFlow")
    def test_callback_alias_carries_deprecation_header(
        self, cre_flow_mock: Any, id_token_mock: Any
    ) -> None:
        id_token_mock.verify_oauth2_token.return_value = {
            "sub": "sub-abc",
            "name": "T",
            "email": "t@x.com",
        }
        cre_flow_mock.instance.return_value.flow.credentials._id_token = "tok"
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["state"] = "xyz"
                resp = client.get("/rest/v1/callback?state=xyz")
                # Header-only: not a redirect to the canonical path (still runs
                # the OAuth flow and lands on /chatbot).
                self.assertEqual(resp.headers.get("Deprecation"), "true")
                self.assertIn("/rest/v1/auth/callback", resp.headers.get("Link", ""))

    # --- login_required content negotiation ---
    def test_login_required_json_returns_401(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get(
                    "/rest/v1/auth/user", headers={"Accept": "application/json"}
                )
                self.assertEqual(resp.status_code, 401)

    def test_login_required_browser_redirects_to_auth_login_with_next(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/auth/user", headers={"Accept": "text/html"})
                self.assertEqual(resp.status_code, 302)
                loc = resp.headers["Location"]
                self.assertTrue(loc.startswith("/rest/v1/auth/login?next="))
                self.assertIn("/rest/v1/auth/user", urllib.parse.unquote(loc))

    def test_login_required_browser_multivalue_accept_redirects(self) -> None:
        # A real browser sends a multi-value Accept; "text/html" is present as a
        # substring, so the browser still gets the 302 (not an exact-match check).
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get(
                    "/rest/v1/auth/user",
                    headers={
                        "Accept": (
                            "text/html,application/xhtml+xml,"
                            "application/xml;q=0.9,*/*;q=0.8"
                        )
                    },
                )
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(
                    resp.headers["Location"].startswith("/rest/v1/auth/login?next=")
                )

    def test_login_required_star_accept_returns_401(self) -> None:
        # curl's default Accept is "*/*": tooling must get a clean 401, NOT a 302
        # into login HTML. This is the key assertion of the inverted default.
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/auth/user", headers={"Accept": "*/*"})
                self.assertEqual(resp.status_code, 401)

    def test_login_required_no_accept_header_returns_401(self) -> None:
        # No Accept header at all (scripts/requests without one) -> 401, not 302.
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/auth/user")
                self.assertEqual(resp.status_code, 401)

    # --- the re-baselined predicate: keyed on user_id, not google_id+name ---
    def test_session_with_google_id_but_no_user_id_is_anonymous(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["google_id"] = "sub-1"
                    sess["name"] = "U"  # but NO user_id
                resp = client.get(
                    "/rest/v1/auth/user", headers={"Accept": "application/json"}
                )
                self.assertEqual(resp.status_code, 401)

    def test_completion_anonymous_json_returns_401(self) -> None:
        # /rest/v1/completion is login_required; an anonymous API client
        # (Accept: application/json) must get a clean 401, not the browser 302
        # toward Google (which the chatbot's fetch would fail to follow).
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.post(
                    "/rest/v1/completion",
                    json={"prompt": "x"},
                    headers={"Accept": "application/json"},
                )
                self.assertEqual(resp.status_code, 401)

    # --- NO_LOGIN dev bypass preserved ---
    def test_no_login_bypasses_login_required(self) -> None:
        with patch.dict(os.environ, {"NO_LOGIN": "1", "INSECURE_REQUESTS": "1"}):
            with self.app.test_client() as client:
                resp = client.get(
                    "/rest/v1/auth/user", headers={"Accept": "application/json"}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.data.decode(), "foobar")


if __name__ == "__main__":
    unittest.main()
