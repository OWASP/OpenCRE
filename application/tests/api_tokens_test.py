"""JWT API tokens: mint (admins), Bearer auth on write/admin/MyOpenCRE, audit log."""

from cre_logging import get_logger

logger = get_logger(__name__)

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import jwt

from application import create_app, sqla
from application.database import db
from application.utils.api_tokens import mint, secret as token_secret


class TestApiTokens(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_no_load_graph = os.environ.get("NO_LOAD_GRAPH_DB")
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        self._env = patch.dict(
            os.environ,
            {
                "API_TOKEN_JWT_SECRET": "test-api-token-jwt-secret-not-for-prod",
                "INSECURE_REQUESTS": "1",
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "LOGIN_ALLOWED_EMAILS": "admin@example.com",
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

    def _session_login(self, client: Any, user: db.User) -> None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
            sess["google_id"] = user.google_sub
            sess["email"] = user.email
            sess["name"] = user.display_name or ""

    def _csrf_headers(self, client: Any) -> dict[str, str]:
        """Seed session CSRF (same path as Admin GET /admin/config)."""
        with client.session_transaction() as sess:
            if not sess.get("csrf_token"):
                import secrets as _secrets

                sess["csrf_token"] = _secrets.token_urlsafe(32)
            token = sess["csrf_token"]
        return {"X-CSRF-Token": token, "Accept": "application/json"}

    def test_secret_uses_env_when_set(self) -> None:
        self.assertEqual(
            token_secret.ensure_api_token_jwt_secret(),
            "test-api-token-jwt-secret-not-for-prod",
        )

    def test_secret_mints_and_persists_when_unset(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_token_jwt_secret"
            with patch.dict(
                os.environ,
                {"API_TOKEN_JWT_SECRET_FILE": str(path)},
                clear=False,
            ):
                os.environ.pop("API_TOKEN_JWT_SECRET", None)
                a = token_secret.ensure_api_token_jwt_secret()
                self.assertTrue(len(a) >= 32)
                self.assertTrue(path.is_file())
                os.environ.pop("API_TOKEN_JWT_SECRET", None)
                b = token_secret.ensure_api_token_jwt_secret()
                self.assertEqual(a, b)

    def test_mint_requires_admin_session(self) -> None:
        with self.app.test_client() as client:
            resp = client.post(
                "/rest/v1/api-keys",
                json={"name": "ci"},
                headers={"Accept": "application/json"},
            )
            self.assertEqual(resp.status_code, 401)

            self._session_login(client, self.outsider)
            resp = client.post("/rest/v1/api-keys", json={"name": "ci"})
            self.assertEqual(resp.status_code, 403)

    def test_mint_list_revoke_and_bearer_put(self) -> None:
        with self.app.test_client() as client:
            self._session_login(client, self.admin)
            csrf = self._csrf_headers(client)
            resp = client.post(
                "/rest/v1/api-keys",
                json={"name": "ci", "expires_days": 30},
                headers=csrf,
            )
            self.assertEqual(resp.status_code, 201, resp.data)
            body = json.loads(resp.data)
            self.assertIn("token", body)
            self.assertIn("jti", body)
            token = body["token"]
            jti = body["jti"]

            listed = json.loads(client.get("/rest/v1/api-keys").data)
            self.assertEqual(len(listed["keys"]), 1)
            self.assertEqual(listed["keys"][0]["jti"], jti)
            self.assertNotIn("token", listed["keys"][0])

        # Bearer (no session) can PUT My OpenCRE resources
        with self.app.test_client() as client:
            resp = client.put(
                "/rest/v1/user/resources",
                json={"selected": ["ASVS"]},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            self.assertEqual(resp.status_code, 200, resp.data)
            self.assertIn("ASVS", json.loads(resp.data)["selected"])

        row = sqla.session.query(db.ApiKeyAuditLog).filter_by(jti=jti).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.method, "PUT")
        self.assertEqual(row.path, "/rest/v1/user/resources")
        self.assertEqual(row.status_code, 200)

        with self.app.test_client() as client:
            self._session_login(client, self.admin)
            csrf = self._csrf_headers(client)
            self.assertEqual(
                client.delete(f"/rest/v1/api-keys/{jti}", headers=csrf).status_code,
                204,
            )

        with self.app.test_client() as client:
            resp = client.put(
                "/rest/v1/user/resources",
                json={"selected": ["ASVS"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_expired_jwt_rejected(self) -> None:
        token = mint.mint_api_token(
            user=self.admin,
            name="expired",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ).token
        with self.app.test_client() as client:
            resp = client.put(
                "/rest/v1/user/resources",
                json={"selected": ["ASVS"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_bad_signature_rejected(self) -> None:
        bad = jwt.encode(
            {
                "jti": "x",
                "sub": self.admin.id,
                "email": self.admin.email,
                "exp": datetime.now(timezone.utc) + timedelta(days=1),
            },
            "wrong-secret",
            algorithm="HS256",
        )
        with self.app.test_client() as client:
            resp = client.put(
                "/rest/v1/user/resources",
                json={"selected": ["ASVS"]},
                headers={"Authorization": f"Bearer {bad}"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_admin_oie_allows_bearer(self) -> None:
        """OIE Admin REST allows API keys for machine ops."""
        minted = mint.mint_api_token(
            user=self.admin,
            name="admin-read",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        with patch.dict(os.environ, {"CRE_ALLOW_IMPORT": "1"}):
            with self.app.test_client() as client:
                resp = client.get(
                    "/admin/oie/rq/status",
                    headers={"Authorization": f"Bearer {minted.token}"},
                )
                self.assertEqual(resp.status_code, 200, resp.data)
