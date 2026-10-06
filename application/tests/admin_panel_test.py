import json
import os
import unittest
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.utils.admin_panel import config_catalog
from application.utils import import_diff


class TestAdminPanel(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_config_rejects_unknown_and_secrets(self) -> None:
        env = {"CRE_ALLOW_IMPORT": "1", "GEMINI_API_KEY": "secret"}
        rows = config_catalog.present_config(env)
        gemini = next(r for r in rows if r["key"] == "GEMINI_API_KEY")
        self.assertEqual(gemini["value"], "***")
        applied, rejected = config_catalog.apply_updates(
            env,
            {
                "GEMINI_API_KEY": "x",
                "NOT_A_KEY": "1",
                "CRE_NOISE_FILTER_BATCH_SIZE": "4",
            },
        )
        self.assertEqual(applied, [])
        self.assertIn("GEMINI_API_KEY", rejected)
        self.assertIn("CRE_NOISE_FILTER_BATCH_SIZE", rejected)
        self.assertEqual(env["GEMINI_API_KEY"], "secret")

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_targets_crud_and_start_and_drop(self) -> None:
        with self.app.test_client() as c:
            r = c.post(
                "/admin/targets",
                json={
                    "id": "asvs-src",
                    "kind": "import_source",
                    "name": "asvs-src",
                },
            )
            self.assertEqual(r.status_code, 201)
            r = c.get("/admin/targets")
            self.assertEqual(r.status_code, 200)
            ids = [t["id"] for t in r.get_json()["targets"]]
            self.assertIn("asvs-src", ids)

            r = c.post("/admin/ingest/start", json={"target_id": "asvs-src"})
            self.assertEqual(r.status_code, 200)
            run_id = r.get_json()["run_id"]
            self.assertTrue(run_id)

            r = c.get("/admin/pipeline")
            self.assertEqual(r.status_code, 200)
            pipe = r.get_json()
            self.assertTrue(pipe["import_runs"])
            self.assertTrue(pipe["events"])

            r = c.post("/admin/imports/drop-last", json={"source": "asvs-src"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["staging_status"], "discarded")

            r = c.delete("/admin/targets/asvs-src")
            self.assertEqual(r.status_code, 200)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_drop_applied_returns_409(self) -> None:
        run = db.create_import_run(source="applied-src", version="v")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json([]),
            staging_status="applied",
        )
        with self.app.test_client() as c:
            r = c.post("/admin/imports/drop-last", json={"source": "applied-src"})
            self.assertEqual(r.status_code, 409)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_edit_mapping_pending(self) -> None:
        run = db.create_import_run(source="map-src", version="v")
        ops = [{"op": "modify", "after": {"description": "old"}}]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=json.dumps(ops),
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(
                f"/admin/imports/runs/{run.id}/mapping",
                json={"op_index": 0, "after": {"description": "new"}},
            )
            self.assertEqual(r.status_code, 200)
            cs = db.get_staged_change_set(run_id=run.id)
            self.assertIn("new", cs.changeset_json)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "OWASP_AGENT_ENABLED": "1"})
    def test_agent_status_requires_import_flag(self) -> None:
        os.environ.pop("CRE_ALLOW_IMPORT", None)
        with self.app.test_client() as c:
            r = c.get("/admin/agent/status")
            self.assertEqual(r.status_code, 404)

    @patch.dict(
        os.environ,
        {
            "NO_LOGIN": "1",
            "OWASP_AGENT_ENABLED": "1",
            "CRE_ALLOW_IMPORT": "1",
            "OWASP_AGENT_DB": "/tmp/owasp_agent.sqlite",
        },
    )
    def test_agent_status(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/agent/status")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertTrue(body["enabled"])
            self.assertFalse(body["writes_cre_graph"])
            self.assertEqual(body["demo_path"], "/chatbot")
            self.assertTrue(body["db_configured"])
            self.assertNotIn("db_path", body)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_config_put_and_get(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/config")
            self.assertEqual(r.status_code, 200)
            r = c.put("/admin/config", json={"updates": {"GEMINI_API_KEY": "nope"}})
            self.assertEqual(r.status_code, 400)
            r = c.put(
                "/admin/config",
                json={"updates": {"CRE_NOISE_FILTER_BATCH_SIZE": "7"}},
            )
            self.assertEqual(r.status_code, 400)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_rerun_creates_run(self) -> None:
        with self.app.test_client() as c:
            r = c.post("/admin/imports/rerun", json={"source": "rerun-src"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json()["run_id"])

    def test_anonymous_json_gets_401(self) -> None:
        with patch.dict(
            os.environ, {"CRE_ALLOW_IMPORT": "1", "INSECURE_REQUESTS": "1"}
        ):
            os.environ.pop("NO_LOGIN", None)
            with self.app.test_client() as c:
                r = c.get("/admin/agent/status", headers={"Accept": "application/json"})
                self.assertEqual(r.status_code, 401)
                r = c.post(
                    "/admin/ingest/start",
                    json={"source": "x"},
                    headers={"Accept": "application/json"},
                )
                self.assertEqual(r.status_code, 401)
