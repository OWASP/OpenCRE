import os
import unittest
from unittest.mock import patch

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_diff, import_pipeline
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

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_imports_endpoints_happy_path(self) -> None:
        run1 = self._import_run_with_std(
            source="admin_api_test", version="run1", desc="one"
        )
        run2 = self._import_run_with_std(
            source="admin_api_test", version="run2", desc="one"
        )

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
        os.environ, {"CRE_ALLOW_IMPORT": "1", "INSECURE_REQUESTS": "1"}, clear=True
    )
    def test_admin_imports_requires_login(self) -> None:
        with self.app.test_client() as c:
            r = c.get("/admin/imports/runs")
            self.assertEqual(r.status_code, 401)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_apply_dry_run_and_apply(self) -> None:
        # Seed current graph and staged changeset.
        self.collection.add_node(
            defs.Standard(
                name="ASVS",
                section="1.1",
                sectionID="V1.1.1",
                description="old",
            )
        )
        run = db.create_import_run(source="admin_apply_test", version="run1")
        ops = [
            import_diff.ModifyControl(
                key=("ASVS", "1.1", "V1.1.1"),
                before={
                    "name": "ASVS",
                    "section": "1.1",
                    "subsection": "",
                    "sectionID": "V1.1.1",
                    "description": "old",
                },
                after={
                    "name": "ASVS",
                    "section": "1.1",
                    "subsection": "",
                    "sectionID": "V1.1.1",
                    "description": "new",
                },
            )
        ]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json(ops),
            has_conflicts=False,
            staging_status="accepted",
        )

        with self.app.test_client() as c:
            r = c.post(f"/admin/imports/runs/{run.id}/apply?dry_run=1")
            self.assertEqual(r.status_code, 200)
            payload = r.get_json()
            self.assertTrue(payload["dry_run"])
            # no mutation on dry-run
            row = (
                sqla.session.query(db.Node)
                .filter(db.Node.name == "ASVS")
                .filter(db.Node.section == "1.1")
                .filter(db.Node.section_id == "V1.1.1")
                .first()
            )
            self.assertEqual(row.description, "old")

            r = c.post(f"/admin/imports/runs/{run.id}/apply")
            self.assertEqual(r.status_code, 200)
            payload = r.get_json()
            self.assertEqual(payload["staging_status"], "applied")
            row = (
                sqla.session.query(db.Node)
                .filter(db.Node.name == "ASVS")
                .filter(db.Node.section == "1.1")
                .filter(db.Node.section_id == "V1.1.1")
                .first()
            )
            self.assertEqual(row.description, "new")

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_apply_requires_accepted_status(self) -> None:
        run = db.create_import_run(source="admin_apply_test", version="run2")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json="[]",
            has_conflicts=False,
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(f"/admin/imports/runs/{run.id}/apply")
            self.assertEqual(r.status_code, 400)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_accept_then_apply(self) -> None:
        self.collection.add_node(
            defs.Standard(
                name="ASVS",
                section="1.1",
                sectionID="V1.1.1",
                description="old",
            )
        )
        run = db.create_import_run(source="accept_flow", version="r1")
        ops = [
            import_diff.ModifyControl(
                key=("ASVS", "1.1", "V1.1.1"),
                before={
                    "name": "ASVS",
                    "section": "1.1",
                    "subsection": "",
                    "sectionID": "V1.1.1",
                    "description": "old",
                },
                after={
                    "name": "ASVS",
                    "section": "1.1",
                    "subsection": "",
                    "sectionID": "V1.1.1",
                    "description": "new",
                },
            )
        ]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json(ops),
            has_conflicts=False,
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            r = c.post(f"/admin/imports/runs/{run.id}/accept")
            self.assertEqual(r.status_code, 200)
            r = c.post(
                f"/admin/imports/runs/{run.id}/apply?skip_post_apply=1",
            )
            self.assertEqual(r.status_code, 200)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_discard_blocks_apply(self) -> None:
        run = db.create_import_run(source="discard_flow", version="r1")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json="[]",
            has_conflicts=False,
            staging_status="pending_review",
        )
        with self.app.test_client() as c:
            self.assertEqual(
                c.post(f"/admin/imports/runs/{run.id}/discard").status_code, 200
            )
            r = c.post(
                f"/admin/imports/runs/{run.id}/accept",
            )
            self.assertEqual(r.status_code, 400)
            r = c.post(f"/admin/imports/runs/{run.id}/apply")
            self.assertEqual(r.status_code, 400)

    @patch.dict(os.environ, {"NO_LOGIN": "1", "CRE_ALLOW_IMPORT": "1"})
    def test_admin_impact_endpoint(self) -> None:
        run = db.create_import_run(source="impact", version="r1")
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json(
                [
                    import_diff.AddControl(
                        key=("X", "s", "id1"),
                        document={
                            "name": "X",
                            "section": "s",
                            "subsection": "",
                            "sectionID": "id1",
                            "description": "d",
                        },
                    )
                ]
            ),
            has_conflicts=False,
        )
        with self.app.test_client() as c:
            r = c.get(f"/admin/imports/runs/{run.id}/impact")
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertIn("impacted_standard_names", j)
            self.assertEqual(j["impacted_standard_names"], ["X"])
