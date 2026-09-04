"""Tests for the /rest/v1/auth/* migration (issue #963, RFC #876 TODO 1).

Canonical auth routes, deprecated aliases (header-only), login_required content
negotiation (browser 302 vs JSON 401), the user_id-keyed session predicate, and
the NO_LOGIN dev bypass. OpenAPI documentation is intentionally out of scope here.
"""

import os
import unittest
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

    @patch("application.web.web_main.id_token")
    @patch("application.web.web_main.CREFlow")
    def test_auth_callback_state_mismatch_returns_without_continuing(
        self, cre_flow_mock: Any, id_token_mock: Any
    ) -> None:
        # Regression for #1021: missing ``return`` on the state-mismatch redirect
        # let the handler continue into token verification / session writes.
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
                    sess["state"] = "expected-state"
                resp = client.get("/rest/v1/auth/callback?state=wrong-state")
                self.assertEqual(resp.status_code, 302)
                self.assertIn("/rest/v1/auth/login", resp.headers.get("Location", ""))
                with client.session_transaction() as sess:
                    self.assertNotIn("user_id", sess)
                    self.assertNotIn("google_id", sess)
        id_token_mock.verify_oauth2_token.assert_not_called()
        self.assertEqual(sqla.session.query(db.User).count(), 0)

    @patch("application.web.web_main.id_token")
    @patch("application.web.web_main.CREFlow")
    @patch("application.web.web_main.db.Node_collection")
    def test_auth_callback_persistence_failure_returns_503(
        self, node_collection_mock: Any, cre_flow_mock: Any, id_token_mock: Any
    ) -> None:
        # If upsert_user fails, we must NOT redirect as if logged in (that leaves
        # a broken session that fails every login_required call). Surface a
        # retryable 503 and leave user_id unset.
        from sqlalchemy.exc import SQLAlchemyError

        id_token_mock.verify_oauth2_token.return_value = {
            "sub": "sub-boom",
            "name": "T",
            "email": "t@example.com",
        }
        cre_flow_mock.instance.return_value.flow.credentials._id_token = "tok"
        node_collection_mock.return_value.upsert_user.side_effect = SQLAlchemyError(
            "db down"
        )
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
                resp = client.get("/rest/v1/auth/callback?state=xyz")
                self.assertEqual(resp.status_code, 503)
                with client.session_transaction() as sess:
                    self.assertNotIn("user_id", sess)

    @patch("application.web.web_main.id_token")
    @patch("application.web.web_main.CREFlow")
    def test_auth_callback_missing_sub_returns_401(
        self, cre_flow_mock: Any, id_token_mock: Any
    ) -> None:
        # No 'sub' claim -> identity can't be established -> explicit 401, not a
        # silently broken session.
        id_token_mock.verify_oauth2_token.return_value = {
            "sub": None,
            "name": "T",
            "email": "t@example.com",
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
                resp = client.get("/rest/v1/auth/callback?state=xyz")
                self.assertEqual(resp.status_code, 401)
                with client.session_transaction() as sess:
                    self.assertNotIn("user_id", sess)

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

    def test_login_required_browser_redirects_to_auth_login(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/auth/user", headers={"Accept": "text/html"})
                self.assertEqual(resp.status_code, 302)
                # Redirect to the constant login route -- no ?next (auth_login does
                # not consume a return target; callback always lands on /chatbot).
                self.assertTrue(
                    resp.headers["Location"].endswith("/rest/v1/auth/login")
                )
                self.assertNotIn("next=", resp.headers["Location"])

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
                    resp.headers["Location"].endswith("/rest/v1/auth/login")
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
