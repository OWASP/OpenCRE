"""Tests for OpenCRE identity resolution (issue #1003 v2).

One user, two doors: a browser session and a Google ID token issued to the
MCP client resolve to the same ``users`` row, but carry different scopes.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from flask import g, session
from werkzeug.exceptions import Forbidden

from application import create_app, sqla
from application.database import db
from application.web import identity

WEB_CLIENT_ID = "web-client.apps.googleusercontent.com"
MCP_CLIENT_ID = "mcp-client.apps.googleusercontent.com"
OTHER_CLIENT_ID = "someone-else.apps.googleusercontent.com"
GOOGLE_SUB = "1076915035000615071"


class IdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        # One patcher owns every variable. Mixing manual os.environ edits with
        # patch.dict leaks: cleanups run after tearDown and re-apply the
        # snapshot taken at start().
        self._env = patch.dict(
            os.environ,
            {
                "NO_LOAD_GRAPH_DB": "1",
                "GOOGLE_CLIENT_ID": WEB_CLIENT_ID,
                "GOOGLE_MCP_CLIENT_ID": MCP_CLIENT_ID,
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        # NO_LOGIN short-circuits every guard; a stray value would hide failures.
        os.environ.pop("NO_LOGIN", None)

        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    # --- helpers ---

    def _seed_user(self, google_sub: str = GOOGLE_SUB):
        return self.collection.upsert_user(
            google_sub=google_sub, email="a@x.com", display_name="U"
        )

    def _claims(self, aud: str = MCP_CLIENT_ID, sub: str = GOOGLE_SUB):
        """A Google ID token as it looks once verified and decoded."""
        return {"sub": sub, "aud": aud, "email": "a@x.com"}

    def _as_token(self, claims=None, side_effect=None):
        """Patch the verification seam; returns a context manager."""
        kwargs = (
            {"side_effect": side_effect}
            if side_effect is not None
            else {"return_value": claims if claims is not None else self._claims()}
        )
        return patch.object(identity, "verify_google_token", **kwargs)

    def _token_request(self):
        return self.app.test_request_context(headers={"Authorization": "Bearer x"})

    def _reset_identity_cache(self) -> None:
        """``g`` lives on the app context, and setUp keeps one pushed for the
        whole test, so the per-request cache survives between request contexts
        here in a way it never would in a real request."""
        g.pop(identity._IDENTITY_KEY, None)

    # --- A. one user, two doors ---

    def test_mcp_token_resolves_to_the_same_user_as_a_session(self) -> None:
        user = self._seed_user()

        with self._as_token():
            with self._token_request():
                token_user, token_channel = identity.current_identity()

        self._reset_identity_cache()
        with self.app.test_request_context():
            session["user_id"] = user.id
            session_user, session_channel = identity.current_identity()

        self.assertEqual(token_user.id, user.id)
        self.assertEqual(session_user.id, user.id)
        self.assertEqual(token_channel, identity.CHANNEL_MCP)
        self.assertEqual(session_channel, identity.CHANNEL_WEB)

    def test_web_audience_token_is_the_web_channel(self) -> None:
        self._seed_user()
        with self._as_token(self._claims(aud=WEB_CLIENT_ID)):
            with self._token_request():
                _, channel = identity.current_identity()
        self.assertEqual(channel, identity.CHANNEL_WEB)

    # --- B. tokens that must be refused ---

    def test_token_with_unknown_audience_is_rejected(self) -> None:
        self._seed_user()
        with self._as_token(self._claims(aud=OTHER_CLIENT_ID)):
            with self._token_request():
                self.assertIsNone(identity.current_identity())

    def test_token_that_fails_verification_is_rejected(self) -> None:
        self._seed_user()
        with self._as_token(side_effect=ValueError("signature mismatch")):
            with self._token_request():
                self.assertIsNone(identity.current_identity())

    def test_token_for_unknown_subject_resolves_to_nobody(self) -> None:
        """A token must never create an account."""
        with self._as_token(self._claims(sub="nobody-has-this-sub")):
            with self._token_request():
                self.assertIsNone(identity.current_identity())
        self.assertIsNone(self.collection.get_user_by_sub("nobody-has-this-sub"))

    def test_request_without_a_credential_is_nobody(self) -> None:
        self._seed_user()
        with self.app.test_request_context():
            self.assertIsNone(identity.current_identity())

    # --- C. scopes ---

    def test_web_channel_gets_all_scopes(self) -> None:
        user = self._seed_user()
        with self.app.test_request_context():
            session["user_id"] = user.id
            self.assertEqual(identity.current_scopes(), identity.ALL_SCOPES)

    def test_mcp_channel_gets_only_granted_scopes(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)

        with self._as_token():
            with self._token_request():
                scopes = identity.current_scopes()

        self.assertIn(identity.SCOPE_MYOPENCRE_READ, scopes)
        self.assertNotIn(identity.SCOPE_MYOPENCRE_WRITE, scopes)

    def test_first_mcp_call_grants_the_default_scopes(self) -> None:
        """Logging in is enough to read; writing stays an explicit choice."""
        user = self._seed_user()
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

        with self._as_token():
            with self._token_request():
                scopes = identity.current_scopes()

        self.assertEqual(scopes, identity.DEFAULT_MCP_SCOPES)
        self.assertIn(identity.SCOPE_MYOPENCRE_READ, scopes)
        self.assertNotIn(identity.SCOPE_MYOPENCRE_WRITE, scopes)

    def test_a_revoked_scope_is_never_restored(self) -> None:
        """The bootstrap must not undo a deliberate revocation."""
        user = self._seed_user()

        with self._as_token():
            with self._token_request():
                identity.current_scopes()

        self.collection.revoke_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

        self._reset_identity_cache()
        with self._as_token():
            with self._token_request():
                scopes = identity.current_scopes()

        self.assertEqual(scopes, ())

    def test_the_session_channel_creates_no_grants(self) -> None:
        user = self._seed_user()
        with self.app.test_request_context():
            session["user_id"] = user.id
            identity.current_scopes()
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

    def test_revoking_a_grant_removes_the_scope(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_WRITE)
        self.collection.revoke_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_WRITE)

        with self._as_token():
            with self._token_request():
                self.assertNotIn(
                    identity.SCOPE_MYOPENCRE_WRITE, identity.current_scopes()
                )

    # --- D. the guards ---

    def test_require_scopes_allows_a_holder_and_blocks_others(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)

        @identity.require_scopes(identity.SCOPE_MYOPENCRE_READ)
        def _read_view():
            return "ok"

        @identity.require_scopes(identity.SCOPE_MYOPENCRE_WRITE)
        def _write_view():
            return "ok"

        with self._as_token():
            with self._token_request():
                self.assertEqual(_read_view(), "ok")
                with self.assertRaises(Forbidden):
                    _write_view()

    def test_session_only_rejects_a_token_caller(self) -> None:
        """A leaked MCP token must not be able to widen its own grants."""
        user = self._seed_user()

        @identity.session_only
        def _grant_view():
            return "ok"

        with self._as_token():
            with self._token_request():
                with self.assertRaises(Forbidden):
                    _grant_view()

        self._reset_identity_cache()
        with self.app.test_request_context():
            session["user_id"] = user.id
            self.assertEqual(_grant_view(), "ok")


if __name__ == "__main__":
    unittest.main()
