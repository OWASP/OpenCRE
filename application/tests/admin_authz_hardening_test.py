"""Staging/production admin allowlist + CSRF + API-key deny."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application import create_app, sqla
from application.database import db


class TestAdminAuthzHardening(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
        os.environ["INSECURE_REQUESTS"] = "1"
        self.app = create_app(mode="test")
        self.app.secret_key = "test-secret"
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_production_empty_emails_blocks_admin(self) -> None:
        with patch.dict(
            os.environ,
            {
                "FLASK_CONFIG": "production",
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ALLOW_IMPORT": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "NO_LOGIN": "0",
                "INSECURE_REQUESTS": "1",
            },
            clear=False,
        ):
            os.environ["LOGIN_ALLOWED_EMAILS"] = ""
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "u1"
                    sess["email"] = "anyone@example.com"
                    sess["google_id"] = "g1"
                resp = client.get("/admin/config")
                self.assertEqual(resp.status_code, 403, resp.data)

    def test_admin_put_requires_csrf(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NO_LOGIN": "0",
                "CRE_ALLOW_IMPORT": "1",
                "CRE_ENABLE_LOGIN": "1",
                "LOGIN_ALLOWED_DOMAINS": "*",
                "LOGIN_ALLOWED_EMAILS": "admin@example.com",
                "FLASK_CONFIG": "development",
                "INSECURE_REQUESTS": "1",
            },
            clear=False,
        ):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "u1"
                    sess["email"] = "admin@example.com"
                    sess["google_id"] = "g1"
                get_resp = client.get("/admin/config")
                self.assertEqual(get_resp.status_code, 200, get_resp.data)
                token = get_resp.get_json().get("csrf_token")
                self.assertTrue(token)
                bad = client.put(
                    "/admin/config",
                    json={"updates": {"OIE_GRAPH_FILING_ENABLED": "0"}},
                )
                self.assertEqual(bad.status_code, 403)
                ok = client.put(
                    "/admin/config",
                    json={"updates": {"OIE_GRAPH_FILING_ENABLED": "0"}},
                    headers={"X-CSRF-Token": token},
                )
                self.assertEqual(ok.status_code, 200, ok.data)


if __name__ == "__main__":
    unittest.main()
