import os
import unittest
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_pipeline
from application.utils.external_project_parsers import base_parser_defs


class TestAdminImportsApi(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        os.environ["INSECURE_REQUESTS"] = "True"
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _import_run_with_std(self, *, source: str, version: str, desc: str) -> str:
        run = db.create_import_run(source=source, version=version)
        std = defs.Standard(
            name="ASVS",
            section="1.1",
            sectionID="V1.1.1",
            description=desc,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.STANDARD,
                subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="test_admin_api",
                extra=[],
            ),
        )
        pr = base_parser_defs.ParseResult(
            results={"ASVS": [std]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr,
            collection=self.collection,
            import_run_id=run.id,
            import_source=run.source,
        )
        return run.id

    @patch.dict(os.environ, {"NO_LOGIN": "1", "ADMIN_IMPORTS_ENABLED": "1"})
    def test_admin_imports_endpoints_happy_path(self) -> None:
        run1 = self._import_run_with_std(source="admin_api_test", version="run1", desc="one")
        run2 = self._import_run_with_std(source="admin_api_test", version="run2", desc="one")

        with self.app.test_client() as c:
            r = c.get("/admin/imports/runs?source=admin_api_test")
            self.assertEqual(r.status_code, 200)
            payload = r.get_json()
            self.assertIn("runs", payload)
            ids = [x["id"] for x in payload["runs"]]
            self.assertIn(run1, ids)
            self.assertIn(run2, ids)

            r = c.get(f"/admin/imports/runs/{run2}")
            self.assertEqual(r.status_code, 200)
            detail = r.get_json()
            self.assertEqual(detail["id"], run2)
            self.assertEqual(detail["source"], "admin_api_test")

            r = c.get(f"/admin/imports/runs/{run2}/changeset")
            self.assertEqual(r.status_code, 200)
            cs = r.get_json()
            self.assertEqual(cs["run_id"], run2)
            self.assertEqual(cs["staging_status"], "pending_review")
            # identical content => empty change set
            self.assertEqual(cs["changeset"], [])

    @patch.dict(os.environ, {"NO_LOGIN": "1", "INSECURE_REQUESTS": "1"}, clear=True)
    def test_admin_imports_disabled_flag_returns_404(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/imports/runs")
            self.assertEqual(r.status_code, 404)

    @patch.dict(
        os.environ, {"ADMIN_IMPORTS_ENABLED": "1", "INSECURE_REQUESTS": "1"}, clear=True
    )
    def test_admin_imports_requires_login(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/imports/runs")
            self.assertEqual(r.status_code, 401)

