"""Web sign-in callback: strict allowed-domain match and a verified Google email.

``evilowasp.org`` must not match ``owasp.org`` (a suffix match let anyone on a
look-alike domain in), and an unverified Google address must never sign in.
A subdomain of an allowed domain (``sub.owasp.org``) is allowed, the same rule
``application.utils.roles`` and the MCP sign-in apply.
"""

import os
import unittest
from typing import Any, Dict, Optional

from application import create_app, sqla  # type: ignore
from application.database import db
from application.tests.env_override import environ_override
from application.web import web_main


class _FakeGoogleFlow:
    """Stands in for the Google OAuth flow: the code exchange always succeeds."""

    def __init__(self) -> None:
        self.credentials = type("Credentials", (), {"_id_token": "tok"})()

    def fetch_token(self, **kwargs: Any) -> None:
        pass


class _FakeCREFlow:
    def __init__(self) -> None:
        self.flow = _FakeGoogleFlow()


class TestAuthCallbackDomain(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_no_load_graph = os.environ.get("NO_LOAD_GRAPH_DB")
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.id_info: Dict[str, Any] = {}
        self.addCleanup(setattr, web_main, "_callback_flow", web_main._callback_flow)
        self.addCleanup(
            setattr,
            web_main,
            "_verify_google_id_token",
            web_main._verify_google_id_token,
        )
        web_main._callback_flow = lambda state: _FakeCREFlow()
        web_main._verify_google_id_token = lambda raw, audience: self.id_info

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()
        if self._prev_no_load_graph is None:
            os.environ.pop("NO_LOAD_GRAPH_DB", None)
        else:
            os.environ["NO_LOAD_GRAPH_DB"] = self._prev_no_load_graph

    def _callback(
        self,
        email: str,
        *,
        verified: Any = True,
        env: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Run the callback for ``email``; returns (response, signed_in)."""
        id_info: Dict[str, Any] = {"sub": "sub-1", "name": "N", "email": email}
        if verified is not None:
            id_info["email_verified"] = verified
        self.id_info = id_info
        environ = {
            "CRE_ENABLE_LOGIN": "1",
            "INSECURE_REQUESTS": "1",
            "LOGIN_ALLOWED_DOMAINS": "owasp.org",
        }
        environ.update(env or {})
        unset = [
            key
            for key in ("ADMIN_EMAILS", "LOGIN_ALLOWED_EMAILS")
            if key not in (env or {})
        ]
        with environ_override(environ, unset=unset):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["state"] = "xyz"
                resp = client.get("/rest/v1/auth/callback?state=xyz")
                with client.session_transaction() as sess:
                    signed_in = "user_id" in sess
        return resp, signed_in

    def test_exact_allowed_domain_signs_in(self) -> None:
        resp, signed_in = self._callback("member@owasp.org")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)

    def test_lookalike_suffix_domain_is_refused(self) -> None:
        resp, signed_in = self._callback("attacker@evilowasp.org")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)
        self.assertEqual(sqla.session.query(db.User).count(), 0)

    def test_lookalike_domain_is_refused_with_a_leading_at_in_the_config(self) -> None:
        resp, signed_in = self._callback(
            "attacker@evilowasp.org", env={"LOGIN_ALLOWED_DOMAINS": "@owasp.org"}
        )
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)

    def test_subdomain_of_an_allowed_domain_is_allowed(self) -> None:
        resp, signed_in = self._callback("member@sub.owasp.org")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)

    def test_a_domain_containing_the_allowed_one_in_the_middle_is_refused(self) -> None:
        resp, signed_in = self._callback("attacker@owasp.org.evil.com")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)

    def test_lookalike_domain_is_refused_in_roles_mode_too(self) -> None:
        resp, signed_in = self._callback(
            "attacker@evilowasp.org", env={"ADMIN_EMAILS": "boss@owasp.org"}
        )
        self.assertIn(resp.status_code, (401, 403))
        self.assertFalse(signed_in)

    def test_unverified_email_is_refused_even_on_an_allowed_domain(self) -> None:
        resp, signed_in = self._callback("member@owasp.org", verified=False)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)
        self.assertEqual(sqla.session.query(db.User).count(), 0)

    def test_missing_email_verified_claim_is_refused(self) -> None:
        resp, signed_in = self._callback("member@owasp.org", verified=None)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)

    def test_leading_dot_domain_config_allows_matching_domains_only(self) -> None:
        env = {"LOGIN_ALLOWED_DOMAINS": ".edu"}
        resp, signed_in = self._callback("m@mit.edu", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)
        resp, signed_in = self._callback("m@evil-edu.com", env=env)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)

    def test_leading_at_domain_config_signs_in_the_domain(self) -> None:
        env = {"LOGIN_ALLOWED_DOMAINS": "@owasp.org"}
        resp, signed_in = self._callback("member@owasp.org", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)

    def test_legacy_mode_applies_the_strict_domain_rule_before_the_email_list(
        self,
    ) -> None:
        env = {"LOGIN_ALLOWED_EMAILS": "attacker@evilowasp.org,member@owasp.org"}
        resp, signed_in = self._callback("attacker@evilowasp.org", env=env)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)
        resp, signed_in = self._callback("member@owasp.org", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)
        resp, signed_in = self._callback("other@owasp.org", env=env)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(signed_in)

    def test_roles_mode_still_signs_in_a_user_on_an_allowed_domain(self) -> None:
        env = {"ADMIN_EMAILS": "boss@owasp.org"}
        resp, signed_in = self._callback("member@owasp.org", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)

    def test_unset_domain_list_is_a_server_error(self) -> None:
        resp, signed_in = self._callback(
            "member@owasp.org", env={"LOGIN_ALLOWED_DOMAINS": ""}
        )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(signed_in)

    def test_email_verified_must_be_the_boolean_true(self) -> None:
        for claim in ("false", "true", "False", 1, "yes", ""):
            with self.subTest(claim=claim):
                resp, signed_in = self._callback("member@owasp.org", verified=claim)
                self.assertEqual(resp.status_code, 401)
                self.assertFalse(signed_in)
        self.assertEqual(sqla.session.query(db.User).count(), 0)

    def test_wildcard_domains_still_need_a_verified_email(self) -> None:
        env = {"LOGIN_ALLOWED_DOMAINS": "*"}
        resp, signed_in = self._callback("a@anywhere.example", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)
        resp, signed_in = self._callback("a@anywhere.example", verified=False, env=env)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)

    def test_named_admin_outside_the_domain_still_needs_a_verified_email(self) -> None:
        env = {"ADMIN_EMAILS": "admin@gmail.com"}
        resp, signed_in = self._callback("Admin@gmail.com", env=env)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(signed_in)
        resp, signed_in = self._callback("Admin@gmail.com", verified=False, env=env)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(signed_in)


if __name__ == "__main__":
    unittest.main()
