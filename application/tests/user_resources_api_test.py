"""Tests for the per-user resource-selection API (issue #586, PR2).

GET/PUT /rest/v1/user/resources, gated by login_required + is_login_enabled.
Flag-off returns a safe default; authenticated users read/write their selection.
"""

import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from application import create_app, sqla
from application.database import db


class TestUserResourcesApi(unittest.TestCase):
    def setUp(self) -> None:
        # SQL-only surface; skip the Neo4j graph load and allow http in tests.
        os.environ["NO_LOAD_GRAPH_DB"] = "1"
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
        os.environ.pop("NO_LOAD_GRAPH_DB", None)

    def _login(self, client: Any, google_sub: str = "sub-1", name: str = "U") -> None:
        with client.session_transaction() as sess:
            sess["google_id"] = google_sub
            sess["name"] = name

    # --- flag off -> safe default, no auth required, no writes ---
    def test_get_returns_default_when_login_disabled(self) -> None:
        with patch.dict(os.environ, {"INSECURE_REQUESTS": "1"}):
            os.environ.pop("CRE_ENABLE_LOGIN", None)
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/user/resources")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": []})

    def test_put_noops_when_login_disabled(self) -> None:
        with patch.dict(os.environ, {"INSECURE_REQUESTS": "1"}):
            os.environ.pop("CRE_ENABLE_LOGIN", None)
            with self.app.test_client() as client:
                resp = client.put(
                    "/rest/v1/user/resources", json={"selected": ["ASVS"]}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": []})
        self.assertEqual(sqla.session.query(db.UserResourceSelection).count(), 0)

    # --- flag on, anonymous -> 401 ---
    def test_get_401_when_anonymous(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/user/resources")
                self.assertEqual(resp.status_code, 401)

    def test_put_401_when_anonymous(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                resp = client.put(
                    "/rest/v1/user/resources", json={"selected": ["ASVS"]}
                )
                self.assertEqual(resp.status_code, 401)

    # --- flag on, authenticated ---
    def test_get_returns_saved_selection(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "CWE"])
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.get("/rest/v1/user/resources")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": ["ASVS", "CWE"]})

    def test_get_returns_empty_for_new_user(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-new", "U")
                resp = client.get("/rest/v1/user/resources")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": []})

    def test_put_persists_and_returns_selection(self) -> None:
        self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.put(
                    "/rest/v1/user/resources", json={"selected": ["CWE", "ASVS"]}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(
                    sorted(json.loads(resp.data)["selected"]), ["ASVS", "CWE"]
                )
                get = client.get("/rest/v1/user/resources")
                self.assertEqual(
                    sorted(json.loads(get.data)["selected"]), ["ASVS", "CWE"]
                )

    def test_put_replaces_previous_selection(self) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "CWE"])
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                client.put("/rest/v1/user/resources", json={"selected": ["SAMM"]})
                get = client.get("/rest/v1/user/resources")
                self.assertEqual(json.loads(get.data)["selected"], ["SAMM"])

    def test_put_dedupes_input(self) -> None:
        self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.put(
                    "/rest/v1/user/resources",
                    json={"selected": ["ASVS", "ASVS", "CWE"]},
                )
                self.assertEqual(
                    sorted(json.loads(resp.data)["selected"]), ["ASVS", "CWE"]
                )

    def test_put_trims_and_dedupes_whitespace_variants(self) -> None:
        # " ASVS " and "ASVS" must normalize to a single stored entry, otherwise
        # they'd persist as distinct rows and defeat the dedupe.
        self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.put(
                    "/rest/v1/user/resources",
                    json={"selected": [" ASVS ", "ASVS", "CWE "]},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(
                    sorted(json.loads(resp.data)["selected"]), ["ASVS", "CWE"]
                )
        self.assertEqual(sqla.session.query(db.UserResourceSelection).count(), 2)

    def test_put_400_on_invalid_body(self) -> None:
        self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        with patch.dict(
            os.environ,
            {
                "CRE_ENABLE_LOGIN": "1",
                "CRE_ENABLE_MYOPENCRE": "1",
                "INSECURE_REQUESTS": "1",
            },
        ):
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                self.assertEqual(
                    client.put(
                        "/rest/v1/user/resources", json={"foo": "bar"}
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.put(
                        "/rest/v1/user/resources", json={"selected": "ASVS"}
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.put(
                        "/rest/v1/user/resources", json={"selected": [1, 2]}
                    ).status_code,
                    400,
                )

    # --- login on but myopencre off -> safe default, no writes ---
    def test_get_returns_default_when_myopencre_disabled(self) -> None:
        # Seed a real, non-empty selection. With myopencre off the endpoint must
        # return the safe default [] instead of it, proving the gate short-circuits
        # BEFORE reading the DB (an empty-user default would pass for the wrong
        # reason). If the gate were bypassed, this would return ["ASVS", "CWE"].
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        self.collection.set_user_resource_selection(user.id, ["ASVS", "CWE"])
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            os.environ.pop("CRE_ENABLE_MYOPENCRE", None)
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.get("/rest/v1/user/resources")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": []})

    def test_put_noops_when_myopencre_disabled(self) -> None:
        self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        with patch.dict(
            os.environ, {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        ):
            os.environ.pop("CRE_ENABLE_MYOPENCRE", None)
            with self.app.test_client() as client:
                self._login(client, "sub-1", "U")
                resp = client.put(
                    "/rest/v1/user/resources", json={"selected": ["ASVS"]}
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(json.loads(resp.data), {"selected": []})
        self.assertEqual(sqla.session.query(db.UserResourceSelection).count(), 0)


if __name__ == "__main__":
    unittest.main()
