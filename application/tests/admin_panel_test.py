import hashlib
import json
import os
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
        agent_db = next(r for r in rows if r["key"] == "OWASP_AGENT_DB")
        self.assertEqual(
            agent_db["help_text"],
            "Postgres URL for the OWASP agent index (not the CRE graph).",
        )
        self.assertNotIn("sqlite", agent_db["help_text"].lower())
        redacted = config_catalog.present_config(
            {
                "OWASP_AGENT_DB": "postgresql://cre:password@127.0.0.1:5432/owasp_agent",
            }
        )
        shown = next(r["value"] for r in redacted if r["key"] == "OWASP_AGENT_DB")
        self.assertEqual(shown, "postgresql://cre:***@127.0.0.1:5432/owasp_agent")
        self.assertNotIn("password", shown)

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
            "OWASP_AGENT_DB": "postgresql://cre:password@127.0.0.1:1/owasp_agent",
        },
    )
    def test_agent_status(self) -> None:
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
            self.assertEqual(
                body["db_url"], "postgresql://cre:***@127.0.0.1:1/owasp_agent"
            )
            self.assertNotIn("password", str(body))
            self.assertNotIn("db_path", body)
            self.assertFalse(body["db_exists"])
            self.assertIsNone(body["counts"])
            self.assertTrue(body["params"])
            help_text = next(
                p["help_text"] for p in body["params"] if p["key"] == "OWASP_AGENT_DB"
            )
            self.assertIn("Postgres", help_text)
            self.assertNotIn("sqlite", help_text.lower())

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_disabled_when_flag_off(self) -> None:
        os.environ.pop("OWASP_AGENT_ENABLED", None)
        with self.app.test_client() as c:
            r = c.get("/admin/agent/status")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.get_json()["enabled"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_ignores_sqlite_file(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NO_LOGIN": "1",
                "CRE_ALLOW_IMPORT": "1",
                "OWASP_AGENT_ENABLED": "1",
                "OWASP_AGENT_DB": "/tmp/owasp_agent_missing_ccdd.sqlite",
            },
        ):
            with patch(
                "application.utils.admin_panel.service.create_engine"
            ) as mock_engine:
                with self.app.test_client() as c:
                    r = c.get("/admin/agent/status")
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertFalse(body["db_configured"])
                self.assertIsNone(body["db_url"])
                self.assertFalse(body["db_exists"])
                self.assertIsNone(body["counts"])
                mock_engine.assert_not_called()

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_agent_status_ignores_sqlite_and_blank_urls(self) -> None:
        for raw in ("sqlite:////tmp/agent.db", "file:/tmp/agent.db", "   "):
            with patch.dict(
                os.environ,
                {
                    "NO_LOGIN": "1",
                    "CRE_ALLOW_IMPORT": "1",
                    "OWASP_AGENT_ENABLED": "1",
                    "OWASP_AGENT_DB": raw,
                },
            ):
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
                    "OWASP_AGENT_DB": "postgres://cre:password@127.0.0.1:5432/owasp_agent",
                },
            ):
                with self.app.test_client() as c:
                    r = c.get("/admin/agent/status")
                    self.assertEqual(r.status_code, 200)
                    body = r.get_json()
                    self.assertEqual(
                        body["db_url"],
                        "postgres://cre:***@127.0.0.1:5432/owasp_agent",
                    )
                    self.assertNotIn("password", str(body))
                    self.assertTrue(body["db_exists"])
                    self.assertEqual(body["counts"]["chapters"], 1)
                    self.assertIsNone(body["last_sync"])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_oie_start_defaults_dry_run_and_no_git_sync(self) -> None:
        oie = {
            "ok": True,
            "stages": [
                {
                    "name": "module_a_harvester",
                    "status": "ok",
                    "detail": "dry",
                }
            ],
        }

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
                mock_oie.assert_called_once_with(
                    r.get_json()["run_id"],
                    repos_yaml=str(service.REPOS_YAML),
                )
                pipe = c.get("/admin/pipeline").get_json()
                stages = {e["stage"] for e in pipe["events"]}
                self.assertIn("module_a_harvester", stages)

                r = c.post(
                    "/admin/ingest/start",
                    json={
                        "target_id": "repo1",
                        "dry_run": False,
                        "sync_repos": True,
                        "run_oie": False,
                    },
                )
                self.assertEqual(r.status_code, 200)
                mock_oie.assert_called_with(
                    r.get_json()["run_id"],
                    repos_yaml=str(service.REPOS_YAML),
                )

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

    def test_invoke_oie_cli_is_dry_run_child_process(self) -> None:
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
        with patch(
            "application.utils.admin_panel.service.subprocess.run", return_value=proc
        ) as mock_run:
            out = service.invoke_oie_cli("run-1")
        self.assertEqual(out["ok"], True)
        argv = mock_run.call_args.args[0]
        self.assertIn("--dry-run", argv)
        self.assertIn("--no-sync-repos", argv)
        self.assertIn("sqlite://", argv)
        self.assertTrue(str(argv[1]).endswith("run_oie_pipeline.py"))
        self.assertNotIn("--repos_yaml", argv)

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
        with patch(
            "application.utils.admin_panel.service.subprocess.run", return_value=proc
        ) as mock_run:
            service.invoke_oie_cli("run-1", repos_yaml="/tmp/custom.yaml")
        argv = mock_run.call_args.args[0]
        self.assertIn("--repos_yaml", argv)
        self.assertIn("/tmp/custom.yaml", argv)

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
    def test_add_org_appends_source_without_github_call(self) -> None:
        packaged_before = service.REPOS_YAML.read_text(encoding="utf-8")
        with patch(
            "application.utils.harvester.github_sources.urllib.request.urlopen"
        ) as mock_open:
            with self.app.test_client() as c:
                r = c.post("/admin/repos.yaml/expand-org", json={"owner": ""})
                self.assertEqual(r.status_code, 400)
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
                self.assertTrue(body["source"].startswith("repos.yaml:"))
                r = c.post(
                    "/admin/repos.yaml/expand-org",
                    json={"yaml": body["yaml"], "owner": "github.com/OWASP/"},
                )
                self.assertEqual(r.get_json()["added"], 0)
            mock_open.assert_not_called()
        self.assertEqual(
            service.REPOS_YAML.read_text(encoding="utf-8"), packaged_before
        )

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

            def _capture(run_id: str, repos_yaml: Optional[str] = None) -> dict:
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
