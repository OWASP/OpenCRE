"""Tests for server-side resource-selection filtering on /rest/v1/standards.

Part of #586 (PR3). A logged-in user with a saved selection sees only their
selected standards (plus OPENCRE); everyone else sees the full list.
``Node_collection.standards`` (Neo4j) is mocked to a fixed list; the User and
selection rows are real on Postgres.
"""

import json
import os
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.utils.gap_analysis import OPENCRE_STANDARD_NAME

STANDARDS = ["ASVS", "CWE", "SAMM", "ZAP"]
FULL = sorted(STANDARDS + [OPENCRE_STANDARD_NAME])


class TestStandardsFilter(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_no_load_graph = os.environ.get("NO_LOAD_GRAPH_DB")
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
        if self._prev_no_load_graph is None:
            os.environ.pop("NO_LOAD_GRAPH_DB", None)
        else:
            os.environ["NO_LOAD_GRAPH_DB"] = self._prev_no_load_graph

    def _login(self, client: Any, google_sub: str = "sub-1", name: str = "U") -> None:
        with client.session_transaction() as sess:
            sess["google_id"] = google_sub
            sess["name"] = name

    def _seed_selection(self, names: List[str]) -> None:
        user = self.collection.upsert_user(
            google_sub="sub-1", email="a@x.com", display_name="U"
        )
        if names:
            self.collection.set_user_resource_selection(user.id, names)

    @staticmethod
    def _enabled() -> Dict[str, str]:
        return {
            "CRE_ENABLE_LOGIN": "1",
            "CRE_ENABLE_MYOPENCRE": "1",
            "INSECURE_REQUESTS": "1",
        }

    # --- the filter applies ---
    @patch.object(db.Node_collection, "standards")
    def test_logged_in_with_selection_filters(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection(["ASVS", "CWE"])
        with patch.dict(os.environ, self._enabled()):
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards")
                self.assertEqual(resp.status_code, 200)
                # Only the selection + OPENCRE; SAMM and ZAP are dropped.
                self.assertEqual(
                    sorted(json.loads(resp.data)),
                    sorted(["ASVS", "CWE", OPENCRE_STANDARD_NAME]),
                )

    @patch.object(db.Node_collection, "standards")
    def test_opencre_always_kept_even_if_not_selected(
        self, standards_mock: Any
    ) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection(["ASVS"])  # OPENCRE not in the selection
        with patch.dict(os.environ, self._enabled()):
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards")
                body = json.loads(resp.data)
                self.assertIn(OPENCRE_STANDARD_NAME, body)
                self.assertEqual(sorted(body), sorted(["ASVS", OPENCRE_STANDARD_NAME]))

    # --- no-op conditions: full list ---
    @patch.object(db.Node_collection, "standards")
    def test_logged_in_empty_selection_returns_full(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection([])  # user exists, no selection
        with patch.dict(os.environ, self._enabled()):
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards")
                self.assertEqual(sorted(json.loads(resp.data)), FULL)

    @patch.object(db.Node_collection, "standards")
    def test_anonymous_returns_full(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        with patch.dict(os.environ, self._enabled()):
            with self.app.test_client() as client:
                resp = client.get("/rest/v1/standards")
                self.assertEqual(sorted(json.loads(resp.data)), FULL)

    @patch.object(db.Node_collection, "standards")
    def test_login_off_returns_full(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection(["ASVS", "CWE"])
        env = {"CRE_ENABLE_MYOPENCRE": "1", "INSECURE_REQUESTS": "1"}
        with patch.dict(os.environ, env):
            os.environ.pop("CRE_ENABLE_LOGIN", None)
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards")
                self.assertEqual(sorted(json.loads(resp.data)), FULL)

    @patch.object(db.Node_collection, "standards")
    def test_myopencre_off_returns_full(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection(["ASVS", "CWE"])
        env = {"CRE_ENABLE_LOGIN": "1", "INSECURE_REQUESTS": "1"}
        with patch.dict(os.environ, env):
            os.environ.pop("CRE_ENABLE_MYOPENCRE", None)
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards")
                self.assertEqual(sorted(json.loads(resp.data)), FULL)

    # --- ?all=true bypass ---
    @patch.object(db.Node_collection, "standards")
    def test_all_true_bypasses_filter(self, standards_mock: Any) -> None:
        standards_mock.return_value = list(STANDARDS)
        self._seed_selection(["ASVS", "CWE"])
        with patch.dict(os.environ, self._enabled()):
            with self.app.test_client() as client:
                self._login(client)
                resp = client.get("/rest/v1/standards?all=true")
                self.assertEqual(sorted(json.loads(resp.data)), FULL)


if __name__ == "__main__":
    unittest.main()
