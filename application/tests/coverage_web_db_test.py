import os
import unittest
from unittest.mock import MagicMock, patch

from rq import job

from application import create_app, sqla  # type: ignore
from application.database import db
from application.defs import cre_defs


class TestDBHelperCoverage(unittest.TestCase):
    def test_db_node_converters(self):
        standard = cre_defs.Standard(
            name="ASVS", section="A", subsection="1", sectionID="x", hyperlink="h"
        )
        code = cre_defs.Code(name="CodeX", description="desc")
        tool = cre_defs.Tool(name="ToolX", tooltype=cre_defs.ToolTypes.Defensive)

        self.assertEqual(
            db.dbNodeFromNode(standard).ntype, cre_defs.Credoctypes.Standard.value
        )
        self.assertEqual(db.dbNodeFromNode(code).ntype, cre_defs.Credoctypes.Code.value)
        self.assertEqual(db.dbNodeFromNode(tool).ntype, cre_defs.Credoctypes.Tool.value)

        fake = cre_defs.Document(name="DocX", doctype=cre_defs.Credoctypes.CRE)  # type: ignore[arg-type]
        self.assertIsNone(db.dbNodeFromNode(fake))  # type: ignore[arg-type]

    def test_node_from_db_and_cre_from_db(self):
        db_std = db.Node(
            name="ASVS",
            ntype=cre_defs.Standard.__name__,
            section="A",
            subsection="1",
            section_id="x",
            link="h",
            tags="a,b",
        )
        out_std = db.nodeFromDB(db_std)
        self.assertEqual(out_std.doctype, cre_defs.Credoctypes.Standard)

        db_tool = db.Node(
            name="ToolX",
            ntype=cre_defs.Tool.__name__,
            section="A",
            section_id="x",
            tags="Defensive,a",
        )
        out_tool = db.nodeFromDB(db_tool)
        self.assertEqual(out_tool.doctype, cre_defs.Credoctypes.Tool)

        db_code = db.Node(name="CodeX", ntype=cre_defs.Code.__name__)
        out_code = db.nodeFromDB(db_code)
        self.assertEqual(out_code.doctype, cre_defs.Credoctypes.Code)

        with self.assertRaises(ValueError):
            db.nodeFromDB(db.Node(name="X", ntype="UnknownType"))

        dbcre = db.CRE(name="C", external_id="123-123", tags="t1,t2")
        cre = db.CREfromDB(dbcre)
        self.assertEqual(cre.id, "123-123")
        roundtrip = db.dbCREfromCRE(cre)
        self.assertEqual(roundtrip.external_id, "123-123")

    def test_cre_from_db_none(self):
        with self.assertRaises(ValueError):
            db.CREfromDB(None)  # type: ignore[arg-type]


class TestWebMainCoverage(unittest.TestCase):
    def setUp(self):
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"

    def tearDown(self):
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def test_capabilities_and_login_logout_no_login(self):
        with patch.dict(os.environ, {"NO_LOGIN": "1", "INSECURE_REQUESTS": "True"}):
            with self.app.test_client() as c:
                cap = c.get("/api/capabilities")
                self.assertEqual(cap.status_code, 200)
                self.assertIn("myopencre", cap.get_json())

                resp = c.get("/rest/v1/login")
                self.assertEqual(resp.status_code, 302)

                user = c.get("/rest/v1/user")
                self.assertEqual(user.status_code, 200)
                self.assertEqual(user.data.decode(), "foobar")

                out = c.get("/rest/v1/logout")
                self.assertEqual(out.status_code, 302)

    def test_before_request_redirect_when_insecure(self):
        with patch.dict(os.environ, {"INSECURE_REQUESTS": ""}, clear=False):
            with self.app.test_client() as c:
                response = c.get("/api/capabilities", base_url="http://localhost")
                self.assertIn(response.status_code, (301, 302))

    @patch("application.web.web_main.prompt_client.PromptHandler")
    def test_chat_completion_with_no_login(self, prompt_mock):
        with patch.dict(os.environ, {"NO_LOGIN": "1", "INSECURE_REQUESTS": "True"}):
            prompt_mock.return_value.generate_text.return_value = {"response": "ok"}
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/completion", json={"prompt": "hello"})
                self.assertEqual(resp.status_code, 200)

    def test_chat_completion_unauthorized(self):
        with patch.dict(os.environ, {"INSECURE_REQUESTS": "True"}, clear=False):
            with self.app.test_client() as c:
                resp = c.post("/rest/v1/completion", json={"prompt": "hello"})
                self.assertEqual(resp.status_code, 401)

    @patch("application.web.web_main.db.Node_collection")
    def test_map_analysis_from_cached_db(self, node_collection_mock):
        collection = MagicMock()
        collection.gap_analysis_exists.return_value = True
        collection.get_gap_analysis_result.return_value = '{"result":"ok"}'
        node_collection_mock.return_value = collection
        with self.app.test_client() as c:
            resp = c.get("/rest/v1/map_analysis?standard=A&standard=B")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json().get("result"), "ok")

    @patch("application.web.web_main.gap_analysis.schedule")
    @patch("application.web.web_main.db.Node_collection")
    def test_map_analysis_heroku_missing_standard_404(
        self, node_collection_mock, schedule_mock
    ):
        collection = MagicMock()
        collection.gap_analysis_exists.return_value = False
        collection.standards.return_value = ["A"]
        node_collection_mock.return_value = collection
        schedule_mock.return_value = {"error": 404}
        with patch.dict(
            os.environ, {"DYNO": "web.1", "INSECURE_REQUESTS": "True"}, clear=False
        ):
            with self.app.test_client() as c:
                resp = c.get("/rest/v1/map_analysis?standard=A&standard=B")
                self.assertEqual(resp.status_code, 404)

    @patch("application.web.web_main.db.Node_collection")
    def test_map_analysis_disabled_404(self, node_collection_mock):
        collection = MagicMock()
        collection.gap_analysis_exists.return_value = False
        node_collection_mock.return_value = collection
        with patch.dict(
            os.environ,
            {"CRE_NO_CALCULATE_GAP_ANALYSIS": "1", "INSECURE_REQUESTS": "True"},
            clear=False,
        ):
            with self.app.test_client() as c:
                resp = c.get("/rest/v1/map_analysis?standard=A&standard=B")
                self.assertEqual(resp.status_code, 404)

    @patch("application.web.web_main.db.Node_collection")
    def test_map_analysis_weak_links(self, node_collection_mock):
        collection = MagicMock()
        collection.get_gap_analysis_result.return_value = '{"result":"ok"}'
        node_collection_mock.return_value = collection
        with self.app.test_client() as c:
            resp = c.get("/rest/v1/map_analysis_weak_links?standard=A&key=K")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json().get("result"), "ok")

    @patch("application.web.web_main.redis.connect")
    @patch("application.web.web_main.job.Job.fetch")
    def test_fetch_job_status_paths(self, fetch_mock, _conn_mock):
        running = MagicMock()
        running.get_status.return_value = job.JobStatus.STARTED
        running.latest_result.return_value = MagicMock(type=MagicMock())
        fetch_mock.return_value = running
        with self.app.test_client() as c:
            resp = c.get("/rest/v1/ma_job_results?id=123")
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
