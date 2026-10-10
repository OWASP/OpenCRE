"""Tests for MCP grants (issue #1003 v2).

Google's device flow only carries ``openid email profile``, so OpenCRE scopes
live in the ``mcp_grants`` table. These cover the storage helpers, the
management endpoints, and the scope check on MyOpenCRE.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.web import identity

WEB_CLIENT_ID = "web-client.apps.googleusercontent.com"
MCP_CLIENT_ID = "mcp-client.apps.googleusercontent.com"
GOOGLE_SUB = "1076915035000615071"
GRANTS_URL = "/rest/v1/user/mcp_grants"
RESOURCES_URL = "/rest/v1/user/resources"


class McpGrantsTest(unittest.TestCase):
    def setUp(self) -> None:
        # One patcher owns every variable. Mixing manual os.environ edits with
        # patch.dict leaks: cleanups run after tearDown and re-apply the
        # snapshot taken at start().
        self._env = patch.dict(os.environ, self._flags())
        self._env.start()
        self.addCleanup(self._env.stop)
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

    @staticmethod
    def _flags() -> Dict[str, str]:
        return {
            "NO_LOAD_GRAPH_DB": "1",
            "CRE_ENABLE_LOGIN": "1",
            "CRE_ENABLE_MYOPENCRE": "1",
            "INSECURE_REQUESTS": "1",
            "GOOGLE_CLIENT_ID": WEB_CLIENT_ID,
            "GOOGLE_MCP_CLIENT_ID": MCP_CLIENT_ID,
        }

    # --- helpers ---

    def _seed_user(self):
        return self.collection.upsert_user(
            google_sub=GOOGLE_SUB, email="a@x.com", display_name="U"
        )

    def _login(self, client: Any, user: Any) -> None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id

    def _as_token(self, sub: str = GOOGLE_SUB):
        claims = {"sub": sub, "aud": MCP_CLIENT_ID, "email": "a@x.com"}
        return patch.object(identity, "verify_google_token", return_value=claims)

    @staticmethod
    def _bearer() -> Dict[str, str]:
        return {"Authorization": "Bearer any-token"}

    # --- A. storage helpers ---

    def test_a_new_user_has_no_grants(self) -> None:
        user = self._seed_user()
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

    def test_bootstrap_grants_defaults_only_once(self) -> None:
        user = self._seed_user()
        first = self.collection.bootstrap_mcp_grants(
            user.id, [identity.SCOPE_MYOPENCRE_READ]
        )
        self.assertEqual(first, [identity.SCOPE_MYOPENCRE_READ])

        self.collection.revoke_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        second = self.collection.bootstrap_mcp_grants(
            user.id, [identity.SCOPE_MYOPENCRE_READ]
        )
        self.assertEqual(second, [])

    def test_add_then_get_returns_the_scope(self) -> None:
        user = self._seed_user()
        granted = self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.assertEqual(granted, [identity.SCOPE_MYOPENCRE_READ])

    def test_adding_the_same_scope_twice_is_idempotent(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        granted = self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.assertEqual(granted, [identity.SCOPE_MYOPENCRE_READ])

    def test_revoke_removes_only_that_scope(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_WRITE)
        granted = self.collection.revoke_mcp_grant(
            user.id, identity.SCOPE_MYOPENCRE_WRITE
        )
        self.assertEqual(granted, [identity.SCOPE_MYOPENCRE_READ])

    def test_a_revoked_scope_can_be_granted_again(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.collection.revoke_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        granted = self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)
        self.assertEqual(granted, [identity.SCOPE_MYOPENCRE_READ])

    def test_grants_do_not_leak_between_users(self) -> None:
        first = self._seed_user()
        second = self.collection.upsert_user(
            google_sub="another-sub", email="b@x.com", display_name="B"
        )
        self.collection.add_mcp_grant(first.id, identity.SCOPE_MYOPENCRE_READ)
        self.assertEqual(self.collection.get_mcp_grants(second.id), [])

    # --- B. the management endpoints ---

    def test_grants_round_trip_over_http(self) -> None:
        user = self._seed_user()
        with self.app.test_client() as client:
            self._login(client, user)

            empty = client.get(GRANTS_URL)
            self.assertEqual(empty.status_code, 200)
            self.assertEqual(empty.get_json(), {"granted": []})

            added = client.put(
                GRANTS_URL, json={"scope": identity.SCOPE_MYOPENCRE_READ}
            )
            self.assertEqual(added.status_code, 200)
            self.assertEqual(
                added.get_json(), {"granted": [identity.SCOPE_MYOPENCRE_READ]}
            )

            removed = client.delete(
                GRANTS_URL, json={"scope": identity.SCOPE_MYOPENCRE_READ}
            )
            self.assertEqual(removed.status_code, 200)
            self.assertEqual(removed.get_json(), {"granted": []})

    def test_an_unknown_scope_is_rejected(self) -> None:
        user = self._seed_user()
        with self.app.test_client() as client:
            self._login(client, user)
            response = client.put(GRANTS_URL, json={"scope": "admin:everything"})
        self.assertEqual(response.status_code, 400)

    def test_a_missing_scope_field_is_rejected(self) -> None:
        user = self._seed_user()
        with self.app.test_client() as client:
            self._login(client, user)
            response = client.put(GRANTS_URL, json={})
        self.assertEqual(response.status_code, 400)

    def test_anonymous_callers_cannot_read_grants(self) -> None:
        self._seed_user()
        with self.app.test_client() as client:
            response = client.get(GRANTS_URL)
        self.assertEqual(response.status_code, 401)

    def test_a_token_caller_cannot_manage_grants(self) -> None:
        """A leaked MCP token must not be able to widen its own grants."""
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)

        with self._as_token():
            with self.app.test_client() as client:
                read = client.get(GRANTS_URL, headers=self._bearer())
                escalate = client.put(
                    GRANTS_URL,
                    json={"scope": identity.SCOPE_MYOPENCRE_WRITE},
                    headers=self._bearer(),
                )

        self.assertEqual(read.status_code, 403)
        self.assertEqual(escalate.status_code, 403)
        self.assertEqual(
            self.collection.get_mcp_grants(user.id),
            [identity.SCOPE_MYOPENCRE_READ],
        )

    # --- C. scopes gate MyOpenCRE ---

    def test_a_read_grant_cannot_write(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_READ)

        with self._as_token():
            with self.app.test_client() as client:
                read = client.get(RESOURCES_URL, headers=self._bearer())
                write = client.put(
                    RESOURCES_URL,
                    json={"selected": ["ASVS"]},
                    headers=self._bearer(),
                )

        self.assertEqual(read.status_code, 200)
        self.assertEqual(write.status_code, 403)

    def test_a_write_grant_can_write(self) -> None:
        user = self._seed_user()
        self.collection.add_mcp_grant(user.id, identity.SCOPE_MYOPENCRE_WRITE)

        with self._as_token():
            with self.app.test_client() as client:
                write = client.put(
                    RESOURCES_URL,
                    json={"selected": ["ASVS"]},
                    headers=self._bearer(),
                )

        self.assertEqual(write.status_code, 200)
        self.assertIn("ASVS", write.get_json()["selected"])

    def test_a_first_time_token_can_read_but_not_write(self) -> None:
        """A fresh MCP client is bootstrapped with the default read scope."""
        user = self._seed_user()
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

        with self._as_token():
            with self.app.test_client() as client:
                read = client.get(RESOURCES_URL, headers=self._bearer())
                write = client.put(
                    RESOURCES_URL,
                    json={"selected": ["ASVS"]},
                    headers=self._bearer(),
                )

        self.assertEqual(read.status_code, 200)
        self.assertEqual(write.status_code, 403)
        self.assertEqual(
            self.collection.get_mcp_grants(user.id),
            [identity.SCOPE_MYOPENCRE_READ],
        )

    def test_a_revoked_scope_stays_revoked_over_http(self) -> None:
        """Revoking from the browser must survive the next MCP call."""
        user = self._seed_user()
        with self._as_token():
            with self.app.test_client() as client:
                client.get(RESOURCES_URL, headers=self._bearer())

        with self.app.test_client() as client:
            self._login(client, user)
            client.delete(GRANTS_URL, json={"scope": identity.SCOPE_MYOPENCRE_READ})

        with self._as_token():
            with self.app.test_client() as client:
                response = client.get(RESOURCES_URL, headers=self._bearer())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.collection.get_mcp_grants(user.id), [])

    def test_a_browser_session_keeps_full_access(self) -> None:
        """Adding scopes must not restrict the human."""
        user = self._seed_user()
        with self.app.test_client() as client:
            self._login(client, user)
            write = client.put(RESOURCES_URL, json={"selected": ["ASVS"]})
            read = client.get(RESOURCES_URL)

        self.assertEqual(write.status_code, 200)
        self.assertEqual(read.status_code, 200)
        self.assertIn("ASVS", read.get_json()["selected"])


if __name__ == "__main__":
    unittest.main()
