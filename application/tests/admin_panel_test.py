import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.utils.admin_panel import config_catalog, service
from application.utils import import_diff

MINIMAL_REPOS_YAML = """repositories:
  - id: owasp-asvs
    type: github
    enabled: true
    owner: OWASP
    repo: ASVS
    branch: master
    paths:
      include:
        - "**/*.md"
    chunking:
      strategy: markdown_heading
      max_tokens: 1200
      overlap_tokens: 100
    polling:
      mode: incremental
      interval_minutes: 60
"""


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
        self.assertFalse(any(r["key"] == "OWASP_AGENT_DB" for r in rows))
        agent_flag = next(r for r in rows if r["key"] == "OWASP_AGENT_ENABLED")
        self.assertIn("main app Postgres", agent_flag["help_text"])
        filing = next(r for r in rows if r["key"] == "OIE_GRAPH_FILING_ENABLED")
        self.assertTrue(filing["writable"])
        self.assertIn("decision_queue", filing["help_text"])
        redacted = config_catalog.present_config(
            {
                "DEV_DATABASE_URL": "postgresql://cre:password@127.0.0.1:5432/opencre",
            }
        )
        shown = next(r["value"] for r in redacted if r["key"] == "DEV_DATABASE_URL")
        self.assertEqual(shown, "postgresql://cre:***@127.0.0.1:5432/opencre")
        self.assertNotIn("password", shown)

    def test_config_can_toggle_graph_filing(self) -> None:
        env: dict = {}
        applied, rejected = config_catalog.apply_updates(
            env, {"OIE_GRAPH_FILING_ENABLED": "true"}
        )
        self.assertEqual(applied, ["OIE_GRAPH_FILING_ENABLED"])
        self.assertEqual(rejected, [])
        self.assertEqual(env["OIE_GRAPH_FILING_ENABLED"], "1")
        applied, rejected = config_catalog.apply_updates(
            env, {"OIE_GRAPH_FILING_ENABLED": "off"}
        )
        self.assertEqual(applied, ["OIE_GRAPH_FILING_ENABLED"])
        self.assertEqual(env["OIE_GRAPH_FILING_ENABLED"], "0")
        applied, rejected = config_catalog.apply_updates(
            env, {"OIE_GRAPH_FILING_ENABLED": "maybe"}
        )
        self.assertEqual(applied, [])
        self.assertIn("OIE_GRAPH_FILING_ENABLED", rejected)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_pipeline_empty_has_queued_strip(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/pipeline")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["import_runs"], [])
            self.assertEqual(body["latest_strip"][0]["id"], "queued")
            self.assertEqual(body["latest_strip"][0]["state"], "current")
            self.assertEqual(body["oie"]["knowledge"], [])

    def test_import_strip_marks_apply_failed(self) -> None:
        strip = service.import_stage_strip("apply_failed")
        self.assertEqual(strip[-1]["id"], "applied")
        self.assertEqual(strip[-1]["state"], "failed")
        self.assertTrue(all(step["state"] == "done" for step in strip[:-1]))

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
            self.assertIn(service.AGENT_RESOURCE_ID, ids)

            r = c.post("/admin/ingest/start", json={"target_id": "asvs-src"})
            self.assertEqual(r.status_code, 200)
            run_id = r.get_json()["run_id"]
            self.assertTrue(run_id)

            r = c.get("/admin/pipeline")
            self.assertEqual(r.status_code, 200)
            pipe = r.get_json()
            self.assertTrue(pipe["import_runs"])
            self.assertTrue(pipe["events"])
            self.assertTrue(pipe["latest_strip"])
            self.assertIn("knowledge", pipe["oie"])
            self.assertEqual(pipe["import_runs"][0]["strip"][1]["id"], "pending_review")
            self.assertEqual(pipe["import_runs"][0]["strip"][1]["state"], "current")

            r = c.post("/admin/imports/drop-last", json={"source": "asvs-src"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["staging_status"], "discarded")

            r = c.delete("/admin/targets/asvs-src")
            self.assertEqual(r.status_code, 200)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_targets_reject_blank_duplicate_and_bad_kind(self) -> None:
        with self.app.test_client() as c:
            r = c.post("/admin/targets", json={})
            self.assertEqual(r.status_code, 400)
            self.assertIn("id and kind", (r.get_json() or {}).get("description", ""))
            r = c.post("/admin/targets", json={"id": "  ", "kind": "import_source"})
            self.assertEqual(r.status_code, 400)
            r = c.post(
                "/admin/targets",
                json={"id": "src", "kind": "not-a-kind"},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn("oie_repo", (r.get_json() or {}).get("description", ""))
            self.assertEqual(
                c.post(
                    "/admin/targets",
                    json={"id": "src", "kind": "import_source"},
                ).status_code,
                201,
            )
            r = c.post(
                "/admin/targets",
                json={"id": "src", "kind": "import_source"},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn("already exists", (r.get_json() or {}).get("description", ""))
            r = c.post(
                "/admin/targets",
                json={"id": service.AGENT_RESOURCE_ID, "kind": "import_source"},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn("built-in", (r.get_json() or {}).get("description", ""))
            r = c.post(
                "/admin/targets",
                json={"id": "agent-extra", "kind": "owasp_agent"},
            )
            self.assertEqual(r.status_code, 400)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_ingest_start_rejects_missing_disabled_and_unknown(self) -> None:
        with self.app.test_client() as c:
            r = c.post("/admin/ingest/start", json={})
            self.assertEqual(r.status_code, 400)
            self.assertIn("source", (r.get_json() or {}).get("description", ""))
            r = c.post("/admin/ingest/start", json={"target_id": "missing"})
            self.assertEqual(r.status_code, 404)
            self.assertEqual(
                (r.get_json() or {}).get("description"), "target not found"
            )
            c.post(
                "/admin/targets",
                json={
                    "id": "off-src",
                    "kind": "import_source",
                    "enabled": False,
                },
            )
            r = c.post("/admin/ingest/start", json={"target_id": "off-src"})
            self.assertEqual(r.status_code, 400)
            self.assertIn("disabled", (r.get_json() or {}).get("description", ""))

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_delete_missing_target_is_json_404(self) -> None:
        with self.app.test_client() as c:
            r = c.delete("/admin/targets/nope")
            self.assertEqual(r.status_code, 404)
            self.assertEqual(
                (r.get_json() or {}).get("description"), "target not found"
            )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_drop_last_requires_source_and_existing_run(self) -> None:
        with self.app.test_client() as c:
            r = c.post("/admin/imports/drop-last", json={})
            self.assertEqual(r.status_code, 400)
            self.assertIn("source", (r.get_json() or {}).get("description", ""))
            r = c.post("/admin/imports/drop-last", json={"source": "ghost"})
            self.assertEqual(r.status_code, 404)
            self.assertIn("no import run", (r.get_json() or {}).get("description", ""))

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_mapping_rejects_bad_payloads(self) -> None:
        run = db.create_import_run(source="map-bad", version="v")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json="not-json",
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(f"/admin/imports/runs/{run.id}/mapping", json={})
            self.assertEqual(r.status_code, 400)
            self.assertIn("op_index", (r.get_json() or {}).get("description", ""))
            r = c.post(
                f"/admin/imports/runs/{run.id}/mapping",
                json={"op_index": 0, "after": {"description": "x"}},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn(
                "invalid changeset", (r.get_json() or {}).get("description", "")
            )
            r = c.post(
                "/admin/imports/runs/missing/mapping",
                json={"op_index": 0, "after": {}},
            )
            self.assertEqual(r.status_code, 404)

        run2 = db.create_import_run(source="map-range", version="v")
        db.persist_staged_change_set(
            run_id=run2.id,
            changeset_json="[]",
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(
                f"/admin/imports/runs/{run2.id}/mapping",
                json={"op_index": 0, "after": {}},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn("out of range", (r.get_json() or {}).get("description", ""))

        run3 = db.create_import_run(source="map-applied", version="v")
        db.persist_staged_change_set(
            run_id=run3.id,
            changeset_json=json.dumps(
                [{"op": "modify_control", "after": {"description": "old"}}]
            ),
            staging_status="applied",
        )
        with self.app.test_client() as c:
            r = c.post(
                f"/admin/imports/runs/{run3.id}/mapping",
                json={"op_index": 0, "after": {"description": "new"}},
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn(
                "pending or accepted", (r.get_json() or {}).get("description", "")
            )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_targets_list_survives_invalid_yaml(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write("{[")
            path = handle.name
        try:
            with patch.object(service, "REPOS_YAML", Path(path)):
                with self.app.test_client() as c:
                    r = c.get("/admin/targets")
            self.assertEqual(r.status_code, 200)
            targets = (r.get_json() or {}).get("targets") or []
            self.assertEqual([t["id"] for t in targets], [service.AGENT_RESOURCE_ID])
            self.assertTrue(targets[0]["built_in"])
            self.assertEqual(targets[0]["kind"], "owasp_agent")
        finally:
            os.unlink(path)

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
            self.assertIn(
                "already applied", (r.get_json() or {}).get("description", "")
            )
            self.assertIn(
                "already applied", (r.get_json() or {}).get("description", "")
            )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_edit_mapping_pending(self) -> None:
        run = db.create_import_run(source="map-src", version="v")
        ops = [{"op": "modify_control", "after": {"description": "old"}}]
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
            self.assertEqual(r.get_json()["field"], "after")
            self.assertTrue(r.get_json()["changeset"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_edit_mapping_add_control_writes_document(self) -> None:
        run = db.create_import_run(source="map-add", version="v")
        ops = [{"op": "add_control", "document": {"description": "old"}}]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=json.dumps(ops),
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(
                f"/admin/imports/runs/{run.id}/mapping",
                json={"op_index": 0, "after": {"description": "added"}},
            )
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["field"], "document")
            cs = db.get_staged_change_set(run_id=run.id)
            data = json.loads(cs.changeset_json)
            self.assertEqual(data[0]["document"]["description"], "added")
            self.assertNotIn("after", data[0])

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
            "DEV_DATABASE_URL": "postgresql://cre:password@127.0.0.1:1/opencre",
        },
        clear=False,
    )
    def test_agent_status(self) -> None:
        os.environ.pop("OWASP_AGENT_DB", None)
        os.environ.pop("DATABASE_URL", None)
        with patch(
            "application.utils.admin_panel.service.create_engine",
            side_effect=OSError("connection refused"),
        ):
            with self.app.test_client() as c:
                r = c.get("/admin/agent/status")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertTrue(body["enabled"])
            self.assertFalse(body["writes_cre_graph"])
            self.assertEqual(body["demo_path"], "/chatbot")
            self.assertTrue(body["db_configured"])
            self.assertEqual(body["db_env_key"], "DEV_DATABASE_URL")
            self.assertEqual(body["db_url"], "postgresql://cre:***@127.0.0.1:1/opencre")
            self.assertNotIn("password", str(body))
            self.assertNotIn("db_path", body)
            self.assertNotIn("OWASP_AGENT_DB", str(body))
            self.assertFalse(body["db_exists"])
            self.assertIsNone(body["counts"])
            self.assertTrue(body["params"])
            help_text = next(
                p["help_text"]
                for p in body["params"]
                if p["key"] == "OWASP_AGENT_ENABLED"
            )
            self.assertIn("main app Postgres", help_text)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_disabled_when_flag_off(self) -> None:
        os.environ.pop("OWASP_AGENT_ENABLED", None)
        with self.app.test_client() as c:
            r = c.get("/admin/agent/status")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.get_json()["enabled"])

    @patch.dict(
        os.environ,
        {
            "NO_LOGIN": "1",
            "CRE_ALLOW_IMPORT": "1",
            "OWASP_AGENT_ENABLED": "1",
            "DEV_DATABASE_URL": "postgresql://cre:password@127.0.0.1:1/opencre",
        },
        clear=False,
    )
    def test_agent_sync_starts_and_records_events(self) -> None:
        os.environ.pop("NEST_API_KEY", None)
        os.environ.pop("OWASP_AGENT_DB", None)
        fake = {
            "status": "ok",
            "sync": {"nest_ok": False, "github_ok": True, "errors": []},
            "concepts": [],
        }
        with patch(
            "application.utils.admin_panel.service._run_agent_sync_job",
            return_value=fake,
        ) as job:
            with self.app.test_client() as c:
                r = c.post(
                    "/admin/agent/sync",
                    json={"wait": True, "auto_concepts": True},
                )
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["source"], "owasp-agent-sync")
            self.assertTrue(body["skip_nest"])
            self.assertFalse(body["async"])
            self.assertEqual(body["result"]["status"], "ok")
            job.assert_called_once()
            run = db.get_import_run(run_id=body["run_id"])
            self.assertIsNotNone(run)
            events = (
                sqla.session.query(db.AdminPipelineEvent)
                .filter(db.AdminPipelineEvent.run_id == body["run_id"])
                .all()
            )
            stages = {e.stage for e in events}
            self.assertIn("queued", stages)
            self.assertIn("agent_sync", stages)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_sync_requires_postgres(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "CRE_ALLOW_IMPORT": "1",
                "DEV_DATABASE_URL": "/tmp/not-postgres.sqlite",
            },
            clear=False,
        ):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("PROD_DATABASE_URL", None)
            with self.app.test_client() as c:
                r = c.post("/admin/agent/sync", json={"wait": True})
            self.assertEqual(r.status_code, 400)
            self.assertIn("Postgres", r.get_json()["description"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_ignores_sqlite_main_db(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "CRE_ALLOW_IMPORT": "1",
                "OWASP_AGENT_ENABLED": "1",
                "DEV_DATABASE_URL": "/tmp/opencre_missing_ccdd.sqlite",
            },
            clear=False,
        ):
            os.environ.pop("OWASP_AGENT_DB", None)
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("PROD_DATABASE_URL", None)
            os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
            with patch(
                "application.utils.admin_panel.service.create_engine"
            ) as mock_engine:
                with self.app.test_client() as c:
                    r = c.get("/admin/agent/status")
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertFalse(body["db_configured"])
                self.assertIsNone(body["db_url"])
                self.assertIsNone(body["db_env_key"])
                self.assertFalse(body["db_exists"])
                self.assertIsNone(body["counts"])
                mock_engine.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_ignores_sqlite_and_blank_main_db(self) -> None:
        for raw in ("sqlite:////tmp/agent.db", "file:/tmp/agent.db", "   "):
            with patch.dict(
                os.environ,
                {
                    "NO_LOGIN": "1",
                    "CRE_ALLOW_IMPORT": "1",
                    "OWASP_AGENT_ENABLED": "1",
                    "DEV_DATABASE_URL": raw,
                },
                clear=False,
            ):
                os.environ.pop("OWASP_AGENT_DB", None)
                os.environ.pop("DATABASE_URL", None)
                os.environ.pop("PROD_DATABASE_URL", None)
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
                with patch(
                    "application.utils.admin_panel.service.create_engine"
                ) as mock_engine:
                    with self.app.test_client() as c:
                        r = c.get("/admin/agent/status")
                    self.assertEqual(r.status_code, 200)
                    body = r.get_json()
                    self.assertFalse(body["db_configured"])
                    self.assertIsNone(body["db_url"])
                    mock_engine.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_counts_postgres(self) -> None:
        class FakeResult:
            def __init__(self, rows: list, scalar_value: int | None = None) -> None:
                self._rows = rows
                self._scalar = scalar_value

            def fetchall(self) -> list:
                return self._rows

            def scalar(self) -> int | None:
                return self._scalar

        class FakeConn:
            def execute(self, stmt: object) -> FakeResult:
                sql = str(stmt)
                if "pg_tables" in sql:
                    return FakeResult([("chapters",)])
                if "COUNT" in sql:
                    return FakeResult([], scalar_value=1)
                return FakeResult([])

            def __enter__(self) -> "FakeConn":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        class FakeEngine:
            def connect(self) -> FakeConn:
                return FakeConn()

            def dispose(self) -> None:
                return None

        with patch(
            "application.utils.admin_panel.service.create_engine",
            return_value=FakeEngine(),
        ):
            with patch.dict(
                os.environ,
                {
                    "NO_LOGIN": "1",
                    "CRE_ALLOW_IMPORT": "1",
                    "OWASP_AGENT_ENABLED": "1",
                    "DEV_DATABASE_URL": "postgres://cre:password@127.0.0.1:5432/opencre",
                },
                clear=False,
            ):
                os.environ.pop("OWASP_AGENT_DB", None)
                os.environ.pop("DATABASE_URL", None)
                with self.app.test_client() as c:
                    r = c.get("/admin/agent/status")
                    self.assertEqual(r.status_code, 200)
                    body = r.get_json()
                    self.assertEqual(
                        body["db_url"],
                        "postgres://cre:***@127.0.0.1:5432/opencre",
                    )
                    self.assertEqual(body["db_env_key"], "DEV_DATABASE_URL")
                    self.assertNotIn("password", str(body))
                    self.assertTrue(body["db_exists"])
                    self.assertEqual(body["counts"]["chapters"], 1)
                    self.assertIsNone(body["last_sync"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_oie_start_defaults_to_live_sync(self) -> None:
        oie = {
            "ok": True,
            "stages": [
                {
                    "name": "module_a_harvester",
                    "status": "ok",
                    "detail": "live",
                }
            ],
        }

        for key in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "VERTEX_PROJECT",
        ):
            os.environ.pop(key, None)

        with patch(
            "application.utils.admin_panel.service.invoke_oie_cli",
            return_value=oie,
        ) as mock_oie:
            with self.app.test_client() as c:
                r = c.post(
                    "/admin/targets",
                    json={"id": "repo1", "kind": "oie_repo", "name": "repo1"},
                )
                self.assertEqual(r.status_code, 201)
                r = c.post("/admin/ingest/start", json={"target_id": "repo1"})
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertFalse(body["dry_run"])
                self.assertTrue(body["sync_repos"])
                mock_oie.assert_called_once_with(
                    body["run_id"],
                    repos_yaml=str(service.REPOS_YAML),
                    dry_run=False,
                    sync_repos=True,
                    max_repos=service.DEFAULT_OIE_MAX_REPOS,
                    skip_b=False,
                    skip_c=False,
                )
                pipe = c.get("/admin/pipeline").get_json()
                stages = {e["stage"] for e in pipe["events"]}
                self.assertIn("module_a_harvester", stages)

                r = c.post(
                    "/admin/ingest/start",
                    json={
                        "target_id": "repo1",
                        "dry_run": True,
                        "sync_repos": False,
                        "max_repos": 2,
                    },
                )
                self.assertEqual(r.status_code, 200)
                mock_oie.assert_called_with(
                    r.get_json()["run_id"],
                    repos_yaml=str(service.REPOS_YAML),
                    dry_run=True,
                    sync_repos=False,
                    max_repos=2,
                    skip_b=False,
                    skip_c=False,
                )

                r = c.post(
                    "/admin/ingest/start",
                    json={"target_id": "repo1", "max_repos": 0},
                )
                self.assertEqual(r.status_code, 400)
                self.assertIn("max_repos", (r.get_json() or {}).get("description", ""))

            with self.app.test_client() as c:
                c.post(
                    "/admin/targets",
                    json={"id": "src1", "kind": "import_source", "name": "src1"},
                )
                mock_oie.reset_mock()
                r = c.post(
                    "/admin/ingest/start",
                    json={"target_id": "src1", "run_oie": True, "dry_run": False},
                )
                self.assertEqual(r.status_code, 200)
                mock_oie.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_config_get_has_restart_instructions(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/config")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertFalse(body["writable"])
            self.assertIn("restart", body["restart_instructions"].lower())

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

    def test_invoke_oie_cli_defaults_to_live_sync(self) -> None:
        from application.utils.admin_panel import service

        for key in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "VERTEX_PROJECT",
        ):
            os.environ.pop(key, None)

        proc = type(
            "P",
            (),
            {
                "stdout": '{"ok": true, "run_id": "run-1", "stages": []}',
                "stderr": "",
                "returncode": 0,
            },
        )()
        pg = "postgresql://cre:password@127.0.0.1:5432/cre"
        with patch.dict(
            os.environ,
            {"DEV_DATABASE_URL": pg, "FLASK_CONFIG": "development"},
            clear=False,
        ):
            os.environ.pop("DATABASE_URL", None)
            with patch(
                "application.utils.admin_panel.service.subprocess.run",
                return_value=proc,
            ) as mock_run:
                out = service.invoke_oie_cli("run-1")
            with patch(
                "application.utils.admin_panel.service.subprocess.run",
                return_value=proc,
            ) as mock_skip:
                service.invoke_oie_cli("run-1", skip_b=True, skip_c=True)
        self.assertEqual(out["ok"], True)
        argv = mock_run.call_args.args[0]
        self.assertNotIn("--dry-run", argv)
        self.assertNotIn("--no-sync-repos", argv)
        self.assertIn("--max-repos", argv)
        self.assertNotIn("--skip-b", argv)
        self.assertNotIn("--skip-c", argv)
        self.assertNotIn("--skip-c1", argv)
        skip_argv = mock_skip.call_args.args[0]
        self.assertIn("--skip-b", skip_argv)
        self.assertIn("--skip-c", skip_argv)
        self.assertNotIn("--skip-c1", skip_argv)
        self.assertNotIn("sqlite://", argv)
        self.assertIn("postgresql+psycopg2://cre:password@127.0.0.1:5432/cre", argv)
        self.assertTrue(str(argv[1]).endswith("run_oie_pipeline.py"))
        self.assertNotIn("--repos_yaml", argv)
        env = mock_run.call_args.kwargs["env"]
        path_parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(path_parts[0], str(service.REPO_ROOT))
        prior = os.environ.get("PYTHONPATH", "")
        for part in prior.split(os.pathsep):
            if part:
                self.assertIn(part, path_parts)

    def test_invoke_oie_cli_honors_dry_run_and_no_sync(self) -> None:
        from application.utils.admin_panel import service

        proc = type(
            "P",
            (),
            {
                "stdout": '{"ok": true, "run_id": "run-1", "stages": []}',
                "stderr": "",
                "returncode": 0,
            },
        )()
        pg = "postgresql://cre:password@127.0.0.1:5432/cre"
        with patch.dict(
            os.environ,
            {"DEV_DATABASE_URL": pg, "FLASK_CONFIG": "development"},
            clear=False,
        ):
            os.environ.pop("DATABASE_URL", None)
            with patch(
                "application.utils.admin_panel.service.subprocess.run",
                return_value=proc,
            ) as mock_run:
                service.invoke_oie_cli(
                    "run-1", dry_run=True, sync_repos=False, max_repos=3
                )
        argv = mock_run.call_args.args[0]
        self.assertIn("--dry-run", argv)
        self.assertIn("--no-sync-repos", argv)
        self.assertIn("--max-repos", argv)
        self.assertIn("3", argv)

    def test_invoke_oie_cli_rejects_missing_postgres(self) -> None:
        from application.utils.admin_panel import service

        drop = {
            "OWASP_AGENT_DB",
            "DATABASE_URL",
            "DEV_DATABASE_URL",
            "PROD_DATABASE_URL",
            "SQLALCHEMY_DATABASE_URI",
            "CRE_CACHE_FILE",
        }
        env = {k: v for k, v in os.environ.items() if k not in drop}
        env["FLASK_CONFIG"] = "development"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                service.invoke_oie_cli("run-1")
        self.assertIn("Postgres", str(ctx.exception))

    def test_invoke_oie_cli_rejects_explicit_sqlite_env(self) -> None:
        from application.utils.admin_panel import service

        with patch.dict(
            os.environ,
            {
                "FLASK_CONFIG": "development",
                "DEV_DATABASE_URL": "sqlite:////tmp/admin.sqlite",
            },
            clear=False,
        ):
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaises(RuntimeError) as ctx:
                service.invoke_oie_cli("run-1")
        self.assertIn("Postgres", str(ctx.exception))

    def test_invoke_oie_cli_passes_repos_yaml(self) -> None:
        proc = type(
            "P",
            (),
            {
                "stdout": '{"ok": true, "run_id": "run-1", "stages": []}',
                "stderr": "",
                "returncode": 0,
            },
        )()
        with patch.dict(
            os.environ,
            {
                "DEV_DATABASE_URL": "postgresql://cre:password@127.0.0.1:5432/cre",
                "FLASK_CONFIG": "development",
            },
            clear=False,
        ):
            os.environ.pop("DATABASE_URL", None)
            with patch(
                "application.utils.admin_panel.service.subprocess.run",
                return_value=proc,
            ) as mock_run:
                service.invoke_oie_cli("run-1", repos_yaml="/tmp/custom.yaml")
        argv = mock_run.call_args.args[0]
        self.assertIn("--repos_yaml", argv)
        self.assertIn("/tmp/custom.yaml", argv)
        env = mock_run.call_args.kwargs["env"]
        self.assertIn(str(service.REPO_ROOT), env["PYTHONPATH"].split(os.pathsep))

    def test_run_oie_pipeline_script_imports_application_without_pythonpath(
        self,
    ) -> None:
        """Admin child is `python /abs/scripts/run_oie_pipeline.py`; sys.path[0]
        is scripts/, not the repo root. Other threads set PYTHONPATH=."""
        script = service.REPO_ROOT / "scripts" / "run_oie_pipeline.py"
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        probe = (
            "import pathlib, sys\n"
            "script = pathlib.Path(sys.argv[1]).resolve()\n"
            "sys.path[0] = str(script.parent)\n"
            "ns = {'__name__': 'not_main', '__file__': str(script)}\n"
            "exec(compile(script.read_text(), str(script), 'exec'), ns)\n"
            "import application\n"
            "print('ok')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe, str(script)],
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("ok", proc.stdout)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_oie_failure_is_logged_as_error(self) -> None:
        with patch(
            "application.utils.admin_panel.service.invoke_oie_cli",
            return_value={"ok": False, "returncode": 1},
        ):
            with self.app.test_client() as c:
                c.post(
                    "/admin/targets",
                    json={"id": "repo-fail", "kind": "oie_repo", "name": "repo-fail"},
                )
                r = c.post("/admin/ingest/start", json={"target_id": "repo-fail"})
                self.assertEqual(r.status_code, 200)
                pipe = c.get("/admin/pipeline").get_json()
                oie_events = [e for e in pipe["events"] if e["stage"] == "oie"]
                self.assertTrue(any(e["status"] == "error" for e in oie_events))

    def test_repos_yaml_source_name(self) -> None:
        digest = hashlib.sha256(b"hello").hexdigest()[:12]
        self.assertEqual(service.repos_yaml_source_name("Nightly", "hello"), "Nightly")
        self.assertEqual(
            service.repos_yaml_source_name("  ", "hello"), f"repos.yaml:{digest}"
        )
        self.assertEqual(
            service.repos_yaml_source_name(None, "hello"), f"repos.yaml:{digest}"
        )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_repos_yaml_get_put_and_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repos.yaml"
            path.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", path):
                with self.app.test_client() as c:
                    r = c.get("/admin/repos.yaml")
                    self.assertEqual(r.status_code, 200)
                    body = r.get_json()
                    self.assertEqual(body["yaml"], MINIMAL_REPOS_YAML)
                    self.assertEqual(
                        body["source"],
                        service.repos_yaml_source_name(None, MINIMAL_REPOS_YAML),
                    )
                    r = c.put("/admin/repos.yaml", json={})
                    self.assertEqual(r.status_code, 400)
                    r = c.put("/admin/repos.yaml", json={"yaml": "repositories: ["})
                    self.assertEqual(r.status_code, 400)
                    self.assertIn(
                        "invalid YAML", (r.get_json() or {}).get("description", "")
                    )
                    r = c.put("/admin/repos.yaml", json={"yaml": "repositories: []"})
                    self.assertEqual(r.status_code, 400)
                    updated = MINIMAL_REPOS_YAML.replace("owasp-asvs", "owasp-asvs-2")
                    r = c.put("/admin/repos.yaml", json={"yaml": updated})
                    self.assertEqual(r.status_code, 200)
                    self.assertTrue(r.get_json()["saved"])
                    self.assertEqual(path.read_text(encoding="utf-8"), updated)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_add_org_probes_github_before_append(self) -> None:
        packaged_before = service.REPOS_YAML.read_text(encoding="utf-8")
        with patch(
            "application.utils.admin_panel.service.probe_github_source"
        ) as probe:
            with self.app.test_client() as c:
                r = c.post("/admin/repos.yaml/expand-org", json={"owner": ""})
                self.assertEqual(r.status_code, 400)
                probe.assert_not_called()
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={"yaml": MINIMAL_REPOS_YAML, "owner": "OWASP"},
                )
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertEqual(body["added"], 1)
                self.assertEqual(body["source_url"], "github.com/OWASP/")
                self.assertIn("github.com/OWASP/", body["yaml"])
                self.assertIn("owasp-asvs", body["yaml"])
                probe.assert_called_once()
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={"yaml": body["yaml"], "owner": "github.com/OWASP/"},
                )
                self.assertEqual(r.get_json()["added"], 0)
                probe.assert_called_once()
        with patch(
            "application.utils.admin_panel.service.probe_github_source",
            side_effect=ValueError(
                "GitHub source is not accessible: github.com/NoSuchOrgCcdd/"
            ),
        ):
            with self.app.test_client() as c:
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={"yaml": MINIMAL_REPOS_YAML, "owner": "NoSuchOrgCcdd"},
                )
                self.assertEqual(r.status_code, 400)
                self.assertIn(
                    "not accessible",
                    (r.get_json() or {}).get("description", ""),
                )
                self.assertIn(
                    "github.com/NoSuchOrgCcdd/",
                    (r.get_json() or {}).get("description", ""),
                )
        self.assertEqual(
            service.REPOS_YAML.read_text(encoding="utf-8"), packaged_before
        )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_save_and_one_off_reject_inaccessible_source(self) -> None:
        yaml_text = "sources:\n  - github.com/NoSuchOrgCcdd/\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repos.yaml"
            path.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", path):
                with patch(
                    "application.utils.admin_panel.service.probe_github_sources",
                    side_effect=ValueError(
                        "GitHub source is not accessible: github.com/NoSuchOrgCcdd/"
                    ),
                ):
                    with patch(
                        "application.utils.admin_panel.service.invoke_oie_cli"
                    ) as mock_oie:
                        with self.app.test_client() as c:
                            r = c.put("/admin/repos.yaml", json={"yaml": yaml_text})
                            self.assertEqual(r.status_code, 400)
                            self.assertIn(
                                "not accessible",
                                (r.get_json() or {}).get("description", ""),
                            )
                            self.assertEqual(
                                path.read_text(encoding="utf-8"), MINIMAL_REPOS_YAML
                            )
                            r = c.post("/admin/ingest/start", json={"yaml": yaml_text})
                            self.assertEqual(r.status_code, 400)
                            mock_oie.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_expand_org_rejects_injected_owner(self) -> None:
        with patch(
            "application.utils.harvester.github_sources.urllib.request.urlopen"
        ) as mock_open:
            with self.app.test_client() as c:
                for owner in ("OWASP?x=1", "OWASP#frag", "..", "x\ny"):
                    r = c.post(
                        "/admin/repos.yaml/expand-org",
                        json={"yaml": MINIMAL_REPOS_YAML, "owner": owner},
                    )
                    self.assertEqual(r.status_code, 400, owner)
            mock_open.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_add_org_keeps_cron_line(self) -> None:
        with patch("application.utils.admin_panel.service.probe_github_source"):
            with self.app.test_client() as c:
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={
                        "yaml": MINIMAL_REPOS_YAML,
                        "owner": "OWASP",
                        "cron": "0 2 * * *",
                    },
                )
                self.assertEqual(r.status_code, 200)
                self.assertIn("0 2 * * *", r.get_json()["yaml"])
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={
                        "yaml": MINIMAL_REPOS_YAML,
                        "owner": "OWASP",
                        "cron": "hourly",
                    },
                )
                self.assertEqual(r.status_code, 400)
                self.assertIn("cron", (r.get_json() or {}).get("description", ""))

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_add_repo_builds_yaml_without_writing_packaged_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "repos.yaml"
            packaged.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", packaged):
                with patch(
                    "application.utils.admin_panel.service.probe_github_source"
                ) as probe:
                    with self.app.test_client() as c:
                        r = c.post(
                            "/admin/repos.yaml/add-repo",
                            json={
                                "yaml": "sources: []\n",
                                "owner": "OWASP",
                                "repo": "ASVS",
                                "id": "one-off-asvs",
                                "include": "**/*.md\ndocs/**/*.md",
                                "strategy": "markdown_heading",
                                "max_tokens": 800,
                                "overlap_tokens": 40,
                                "cron": "0 * * * *",
                            },
                        )
                        self.assertEqual(r.status_code, 200)
                        body = r.get_json()
                        self.assertEqual(body["added"], "one-off-asvs")
                        self.assertIn("0 * * * *", body["yaml"])
                        self.assertIn("one-off-asvs", body["yaml"])
                        self.assertEqual(
                            packaged.read_text(encoding="utf-8"), MINIMAL_REPOS_YAML
                        )
                        probe.assert_called_once()
                        r = c.post(
                            "/admin/repos.yaml/add-repo",
                            json={"yaml": "sources: []\n", "owner": "OWASP"},
                        )
                        self.assertEqual(r.status_code, 400)
                        self.assertIn(
                            "owner and repo",
                            (r.get_json() or {}).get("description", ""),
                        )
                        r = c.post(
                            "/admin/repos.yaml/add-repo",
                            json={
                                "yaml": "sources: []\n",
                                "owner": "OWASP",
                                "repo": "ASVS",
                                "max_tokens": "nope",
                            },
                        )
                        self.assertEqual(r.status_code, 400)
                        self.assertIn(
                            "max_tokens", (r.get_json() or {}).get("description", "")
                        )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_packaged_ingest_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "repos.yaml"
            packaged.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", packaged):
                with patch(
                    "application.utils.admin_panel.service.invoke_oie_cli",
                    return_value={"ok": True, "stages": []},
                ) as mock_oie:
                    with self.app.test_client() as c:
                        r = c.post("/admin/ingest/start", json={"packaged": True})
                        self.assertEqual(r.status_code, 200)
                        self.assertEqual(
                            r.get_json()["source"],
                            service.repos_yaml_source_name(None, MINIMAL_REPOS_YAML),
                        )
                        mock_oie.assert_called_once()
                        r = c.post("/admin/ingest/start", json={"current": True})
                        self.assertEqual(r.status_code, 200)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_dashboard_payload(self) -> None:
        run = db.create_import_run(source="dash-src", version="v")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json="[]",
            staging_status="pending_review",
        )
        service.append_event(run.id, "oie", "started", "running")
        service.append_event(run.id, "oie", "error", "boom")
        with self.app.test_client() as c:
            r = c.get("/admin/dashboard")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertTrue(body["running"])
            self.assertTrue(body["failed"])
            self.assertEqual(body["import_runs"][0]["source"], "dash-src")
            self.assertIn("agent", body)
            self.assertFalse(body["agent"]["writes_cre_graph"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_review_links_approve_deny_relink(self) -> None:
        run = db.create_import_run(source="link-src", version="v")
        ops = [
            {
                "op": "add_control",
                "document": {
                    "name": "ASVS",
                    "section": "1.1",
                    "linked_cres": [{"id": "123", "name": "Auth"}],
                },
            },
            {"op": "add_control", "document": {"name": "Orphan", "linked_cres": []}},
            {
                "op": "modify_control",
                "key": [],
                "after": {
                    "linked_cres": [{"id": "9", "name": "Old"}],
                },
            },
        ]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=json.dumps(ops),
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.get(f"/admin/imports/runs/{run.id}/links")
            self.assertEqual(r.status_code, 200)
            links = r.get_json()["links"]
            self.assertEqual(links[0]["linked_to"]["id"], "123")
            self.assertIsNone(links[1]["linked_to"])
            self.assertEqual(links[2]["added"]["name"], "")
            r = c.post(
                f"/admin/imports/runs/{run.id}/links",
                json={"op_index": 0, "link_index": 0, "action": "approve"},
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["links"][0]["decision"], "approved")
            r = c.post(
                f"/admin/imports/runs/{run.id}/links",
                json={
                    "op_index": 0,
                    "link_index": 0,
                    "action": "relink",
                    "cre": {"id": "456", "name": "Session"},
                },
            )
            self.assertEqual(r.get_json()["links"][0]["linked_to"]["id"], "456")
            r = c.post(
                f"/admin/imports/runs/{run.id}/links",
                json={"op_index": 0, "link_index": 0, "action": "deny"},
            )
            self.assertEqual(r.status_code, 200)
            remaining = r.get_json()["links"]
            self.assertTrue(
                all(
                    row["op_index"] != 0 or row["linked_to"] is None
                    for row in remaining
                )
            )
            r = c.post(
                f"/admin/imports/runs/{run.id}/links",
                json={
                    "op_index": 1,
                    "action": "relink",
                    "cre": {"name": "Access Control"},
                },
            )
            self.assertEqual(r.status_code, 200)
            added = [row for row in r.get_json()["links"] if row["op_index"] == 1]
            self.assertEqual(added[0]["linked_to"]["name"], "Access Control")
            r = c.post(
                f"/admin/imports/runs/{run.id}/links",
                json={"op_index": 0, "action": "nope"},
            )
            self.assertEqual(r.status_code, 400)
            r = c.post(f"/admin/imports/runs/{run.id}/links", json={"op_index": 0})
            self.assertEqual(r.status_code, 400)
            r = c.get("/admin/imports/runs/missing/links")
            self.assertEqual(r.status_code, 404)

    def test_present_config_includes_env_example_keys(self) -> None:
        keys = config_catalog.keys_from_env_example()
        self.assertIn("DEV_DATABASE_URL", keys)
        self.assertNotIn("OWASP_AGENT_DB", keys)
        self.assertIn("OWASP_AGENT_ENABLED", keys)
        self.assertIn("CRE_ENABLE_LOGIN", keys)
        rows = config_catalog.present_config(
            {
                "DEV_DATABASE_URL": "postgresql://cre:secret@localhost/opencre",
                "GOOGLE_CLIENT_SECRET": "shh",
                "CRE_ALLOW_IMPORT": "1",
            }
        )
        by_key = {row["key"]: row for row in rows}
        for key in keys:
            self.assertIn(key, by_key)
        self.assertIn("CRE_ALLOW_IMPORT", by_key)
        self.assertEqual(
            by_key["DEV_DATABASE_URL"]["value"],
            "postgresql://cre:***@localhost/opencre",
        )
        self.assertEqual(by_key["GOOGLE_CLIENT_SECRET"]["value"], "***")
        self.assertTrue(by_key["GOOGLE_CLIENT_SECRET"]["secret"])
        self.assertEqual(by_key["CRE_ALLOW_IMPORT"]["value"], "1")

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_config_get_lists_env_example_keys(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/config")
            self.assertEqual(r.status_code, 200)
            keys = {row["key"] for row in r.get_json()["config"]}
            for expected in config_catalog.keys_from_env_example():
                self.assertIn(expected, keys)
            self.assertIn("CRE_ALLOW_IMPORT", keys)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_repos_yaml_rejects_oversized_payload(self) -> None:
        huge = "a" * (service.YAML_MAX_BYTES + 1)
        with self.app.test_client() as c:
            r = c.put("/admin/repos.yaml", json={"yaml": huge})
            self.assertEqual(r.status_code, 400)
            self.assertIn(
                service.YAML_MAX_LABEL,
                (r.get_json() or {}).get("description", ""),
            )
            r = c.post("/admin/ingest/start", json={"yaml": huge})
            self.assertEqual(r.status_code, 400)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_one_off_yaml_uses_custom_name_or_hash_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "repos.yaml"
            packaged.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            seen: dict = {}

            def _capture(
                run_id: str, repos_yaml: Optional[str] = None, **_kwargs: object
            ) -> dict:
                seen["run_id"] = run_id
                seen["repos_yaml"] = repos_yaml
                if repos_yaml:
                    seen["text"] = Path(repos_yaml).read_text(encoding="utf-8")
                return {"ok": True, "stages": []}

            one_off = MINIMAL_REPOS_YAML.replace("owasp-asvs", "one-off-asvs")
            with patch.object(service, "REPOS_YAML", packaged):
                with patch(
                    "application.utils.admin_panel.service.invoke_oie_cli",
                    side_effect=_capture,
                ):
                    with self.app.test_client() as c:
                        r = c.post("/admin/ingest/start", json={"yaml": "nope: ["})
                        self.assertEqual(r.status_code, 400)
                        r = c.post(
                            "/admin/ingest/start",
                            json={"yaml": one_off, "name": "nightly-asvs"},
                        )
                        self.assertEqual(r.status_code, 200)
                        self.assertEqual(r.get_json()["source"], "nightly-asvs")
                        self.assertEqual(seen["text"], one_off)
                        self.assertFalse(Path(seen["repos_yaml"]).exists())
                        self.assertEqual(
                            packaged.read_text(encoding="utf-8"), MINIMAL_REPOS_YAML
                        )

                        r = c.post("/admin/ingest/start", json={"yaml": one_off})
                        self.assertEqual(r.status_code, 200)
                        expected = service.repos_yaml_source_name(None, one_off)
                        self.assertEqual(r.get_json()["source"], expected)
                        pipe = c.get("/admin/pipeline").get_json()
                        sources = [row["source"] for row in pipe["import_runs"]]
                        self.assertIn("nightly-asvs", sources)
                        self.assertIn(expected, sources)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_oie_repo_start_source_is_yaml_hash_or_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "repos.yaml"
            packaged.write_text(MINIMAL_REPOS_YAML, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", packaged):
                with patch(
                    "application.utils.admin_panel.service.invoke_oie_cli",
                    return_value={"ok": True, "stages": []},
                ):
                    with self.app.test_client() as c:
                        c.post(
                            "/admin/targets",
                            json={"id": "repo-hash", "kind": "oie_repo"},
                        )
                        r = c.post(
                            "/admin/ingest/start", json={"target_id": "repo-hash"}
                        )
                        self.assertEqual(r.status_code, 200)
                        self.assertEqual(
                            r.get_json()["source"],
                            service.repos_yaml_source_name(None, MINIMAL_REPOS_YAML),
                        )
                        r = c.post(
                            "/admin/ingest/start",
                            json={"target_id": "repo-hash", "name": "custom-oie"},
                        )
                        self.assertEqual(r.get_json()["source"], "custom-oie")

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_built_in_agent_is_a_resource_not_a_crud_row(self) -> None:
        for key in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "VERTEX_PROJECT",
        ):
            os.environ.pop(key, None)
        with patch(
            "application.utils.admin_panel.service.invoke_oie_cli",
            return_value={"ok": True, "stages": []},
        ) as mock_oie:
            with self.app.test_client() as c:
                r = c.get("/admin/targets")
                self.assertEqual(r.status_code, 200)
                agent = next(
                    t
                    for t in r.get_json()["targets"]
                    if t["id"] == service.AGENT_RESOURCE_ID
                )
                self.assertEqual(agent["kind"], "owasp_agent")
                self.assertTrue(agent["built_in"])
                self.assertIn("enabled", agent["spec"])
                self.assertFalse(agent["spec"]["writes_cre_graph"])

                r = c.delete(f"/admin/targets/{service.AGENT_RESOURCE_ID}")
                self.assertEqual(r.status_code, 400)
                self.assertIn("built-in", (r.get_json() or {}).get("description", ""))

                leftover = db.IngestionTarget(
                    id=service.AGENT_RESOURCE_ID,
                    kind="import_source",
                    name="ghost",
                    spec_json="{}",
                    enabled=True,
                    created_at=service._now(),
                )
                sqla.session.add(leftover)
                sqla.session.commit()
                r = c.delete(f"/admin/targets/{service.AGENT_RESOURCE_ID}")
                self.assertEqual(r.status_code, 200)
                self.assertIsNone(
                    sqla.session.query(db.IngestionTarget)
                    .filter_by(id=service.AGENT_RESOURCE_ID)
                    .first()
                )
                ids = [t["id"] for t in c.get("/admin/targets").get_json()["targets"]]
                self.assertIn(service.AGENT_RESOURCE_ID, ids)

                r = c.post(
                    "/admin/ingest/start",
                    json={"target_id": service.AGENT_RESOURCE_ID},
                )
                self.assertEqual(r.status_code, 200)
                mock_oie.assert_called_once_with(
                    r.get_json()["run_id"],
                    repos_yaml=str(service.REPOS_YAML),
                    dry_run=False,
                    sync_repos=True,
                    max_repos=service.DEFAULT_OIE_MAX_REPOS,
                    skip_b=False,
                    skip_c=False,
                )

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_yaml_seed_skips_reserved_agent_id(self) -> None:
        reserved = f"""repositories:
  - id: {service.AGENT_RESOURCE_ID}
    type: github
    enabled: true
    owner: OWASP
    repo: ASVS
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repos.yaml"
            path.write_text(reserved, encoding="utf-8")
            with patch.object(service, "REPOS_YAML", path):
                with self.app.test_client() as c:
                    r = c.get("/admin/targets")
                    self.assertEqual(r.status_code, 200)
                    targets = r.get_json()["targets"]
                    self.assertEqual(
                        [t["id"] for t in targets], [service.AGENT_RESOURCE_ID]
                    )
                    self.assertTrue(targets[0]["built_in"])
                    self.assertIsNone(
                        sqla.session.query(db.IngestionTarget)
                        .filter_by(id=service.AGENT_RESOURCE_ID)
                        .first()
                    )

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
                r = c.get("/admin/repos.yaml", headers={"Accept": "application/json"})
                self.assertEqual(r.status_code, 401)
                r = c.get("/admin/dashboard", headers={"Accept": "application/json"})
                self.assertEqual(r.status_code, 401)
