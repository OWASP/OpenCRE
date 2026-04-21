"""Phase 2 staging persistence tests (snapshots + change sets)."""

import unittest

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_apply, import_diff, import_pipeline
from application.utils.external_project_parsers import base_parser_defs


class TestImportStaging(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def _std(self, desc: str) -> defs.Standard:
        return defs.Standard(
            name="ASVS",
            section="1.1",
            sectionID="V1.1.1",
            description=desc,
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.STANDARD,
                subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="test_phase2",
                extra=[],
            ),
        )

    def test_snapshot_persisted_per_run(self) -> None:
        run = db.create_import_run(source="test_phase2", version="run1")
        pr = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("one")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr,
            collection=self.collection,
            import_run_id=run.id,
            import_source=run.source,
        )
        snap = db.get_standard_snapshot(run_id=run.id, standard_name="ASVS")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.standard_name, "ASVS")
        self.assertTrue(snap.snapshot_json)
        self.assertTrue(snap.content_hash)

    def test_identical_reimport_yields_empty_changeset(self) -> None:
        pr = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("same")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )

        run1 = db.create_import_run(source="test_phase2", version="run1")
        import_pipeline.apply_parse_result(
            parse_result=pr,
            collection=self.collection,
            import_run_id=run1.id,
            import_source=run1.source,
        )

        run2 = db.create_import_run(source="test_phase2", version="run2")
        import_pipeline.apply_parse_result(
            parse_result=pr,
            collection=self.collection,
            import_run_id=run2.id,
            import_source=run2.source,
        )

        cs = db.get_staged_change_set(run_id=run2.id)
        self.assertIsNotNone(cs)
        self.assertEqual(cs.staging_status, "pending_review")
        ops = import_diff.change_set_from_json(cs.changeset_json)
        self.assertEqual(ops, [])

    def test_modified_reimport_yields_modify_op(self) -> None:
        run1 = db.create_import_run(source="test_phase2", version="run1")
        pr1 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("old")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr1,
            collection=self.collection,
            import_run_id=run1.id,
            import_source=run1.source,
        )

        run2 = db.create_import_run(source="test_phase2", version="run2")
        pr2 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("new")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr2,
            collection=self.collection,
            import_run_id=run2.id,
            import_source=run2.source,
        )

        cs = db.get_staged_change_set(run_id=run2.id)
        ops = import_diff.change_set_from_json(cs.changeset_json if cs else "[]")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op, "modify_control")

    def test_manual_edit_sets_has_conflicts(self) -> None:
        run1 = db.create_import_run(source="test_phase2", version="m1")
        pr1 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("synced")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr1,
            collection=self.collection,
            import_run_id=run1.id,
            import_source=run1.source,
        )
        row = (
            sqla.session.query(db.Node)
            .filter(db.Node.name == "ASVS")
            .filter(db.Node.section == "1.1")
            .filter(db.Node.section_id == "V1.1.1")
            .first()
        )
        self.assertIsNotNone(row)
        row.description = "edited_out_of_band"
        sqla.session.add(row)
        sqla.session.commit()

        run2 = db.create_import_run(source="test_phase2", version="m2")
        pr2 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("from_upstream")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr2,
            collection=self.collection,
            import_run_id=run2.id,
            import_source=run2.source,
        )
        cs = db.get_staged_change_set(run_id=run2.id)
        self.assertIsNotNone(cs)
        self.assertTrue(cs.has_conflicts)

    def test_e2e_previous_import_then_staged_second_import_accept_apply_idempotent(
        self,
    ) -> None:
        """
        Full pipeline diff is persisted for run 2, but DB stays on run 1 until apply.

        (``apply_parse_result`` for run 2 would commit immediately and make apply's
        optimistic ``before`` check fail; ``stage_parse_result_only`` matches
        review-then-apply semantics.)
        """
        source = "e2e_staging_apply"

        run1 = db.create_import_run(source=source, version="v1")
        pr1 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("from_run_one")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.apply_parse_result(
            parse_result=pr1,
            collection=self.collection,
            import_run_id=run1.id,
            import_source=source,
        )

        run2 = db.create_import_run(source=source, version="v2")
        pr2 = base_parser_defs.ParseResult(
            results={"ASVS": [self._std("from_run_two")]},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
        import_pipeline.stage_parse_result_only(
            parse_result=pr2,
            collection=self.collection,
            import_run_id=run2.id,
            import_source=source,
        )

        row = (
            sqla.session.query(db.Node)
            .filter(db.Node.name == "ASVS")
            .filter(db.Node.section == "1.1")
            .filter(db.Node.section_id == "V1.1.1")
            .first()
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.description, "from_run_one")

        cs = db.get_staged_change_set(run_id=run2.id)
        self.assertIsNotNone(cs)
        self.assertEqual(cs.staging_status, "pending_review")
        self.assertFalse(cs.has_conflicts)
        ops = import_diff.change_set_from_json(cs.changeset_json or "[]")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op, "modify_control")
        mod = ops[0]
        self.assertEqual(mod.before.get("description"), "from_run_one")
        self.assertEqual(mod.after.get("description"), "from_run_two")

        db.update_staged_change_set(run_id=run2.id, staging_status="accepted")
        res = import_apply.apply_changeset(
            run_id=run2.id,
            dry_run=False,
            db_connection_str="",
            run_post_apply_effects=False,
        )
        self.assertEqual(res.staging_status, "applied")
        self.assertFalse(res.already_applied)

        sqla.session.refresh(row)
        self.assertEqual(row.description, "from_run_two")

        res2 = import_apply.apply_changeset(
            run_id=run2.id,
            dry_run=False,
            db_connection_str="",
            run_post_apply_effects=False,
        )
        self.assertTrue(res2.already_applied)
