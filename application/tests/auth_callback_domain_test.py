"""Web sign-in callback: strict allowed-domain match and a verified Google email.

``evilowasp.org`` must not match ``owasp.org`` (a suffix match let anyone on a
look-alike domain in), and an unverified Google address must never sign in.
A subdomain of an allowed domain (``sub.owasp.org``) is allowed, the same rule
``application.utils.roles`` and the MCP sign-in apply.
"""

import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from application import create_app, sqla  # type: ignore
from application.database import db


class TestAuthCallbackDomain(unittest.TestCase):
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

    def _callback(
        self,
        email: str,
        *,
        verified: Optional[bool] = True,
        env: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Run the callback for ``email``; returns (response, signed_in)."""
        id_info: Dict[str, Any] = {"sub": "sub-1", "name": "N", "email": email}
        if verified is not None:
            id_info["email_verified"] = verified
        environ = {
            "CRE_ENABLE_LOGIN": "1",
            "INSECURE_REQUESTS": "1",
            "LOGIN_ALLOWED_DOMAINS": "owasp.org",
        }
        environ.update(env or {})
        with patch("application.web.web_main.id_token") as id_token_mock, patch(
            "application.web.web_main.CREFlow"
        ) as flow:
            id_token_mock.verify_oauth2_token.return_value = id_info
            flow.instance.return_value.flow.credentials._id_token = "tok"
            with patch.dict(os.environ, environ):
                for key in ("ADMIN_EMAILS", "LOGIN_ALLOWED_EMAILS"):
                    if key not in (env or {}):
                        os.environ.pop(key, None)
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
