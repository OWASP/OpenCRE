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
        agent_db = next(r for r in rows if r["key"] == "OWASP_AGENT_DB")
        self.assertIn("Postgres", agent_db["help_text"])
        self.assertNotIn("sqlite", agent_db["help_text"].lower())
        self.assertNotIn("SQLite", agent_db["help_text"])

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
                body["db_url"], "postgresql://cre:password@127.0.0.1:1/owasp_agent"
            )
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
            with self.app.test_client() as c:
                r = c.get("/admin/agent/status")
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertFalse(body["db_configured"])
                self.assertIsNone(body["db_url"])
                self.assertFalse(body["db_exists"])
                self.assertIsNone(body["counts"])

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
                        "postgres://cre:password@127.0.0.1:5432/owasp_agent",
                    )
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
                mock_oie.assert_called_once_with(r.get_json()["run_id"])
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
                mock_oie.assert_called_with(r.get_json()["run_id"])

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
