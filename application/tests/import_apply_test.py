import unittest

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_apply, import_diff


class TestImportApply(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _mk_std(self, desc: str) -> defs.Standard:
        return defs.Standard(
            name="ASVS",
            section="1.1",
            sectionID="V1.1.1",
            description=desc,
        )

    def test_apply_happy_path_and_idempotent(self) -> None:
        self.collection.add_node(self._mk_std("old"))
        run = db.create_import_run(source="apply_test", version="run1")
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

        res = import_apply.apply_changeset(run_id=run.id, dry_run=False)
        self.assertEqual(res.staging_status, "applied")
        row = (
            sqla.session.query(db.Node)
            .filter(db.Node.name == "ASVS")
            .filter(db.Node.section == "1.1")
            .filter(db.Node.section_id == "V1.1.1")
            .first()
        )
        self.assertEqual(row.description, "new")

        res2 = import_apply.apply_changeset(run_id=run.id, dry_run=False)
        self.assertTrue(res2.already_applied)

    def test_apply_dry_run_no_mutation(self) -> None:
        run = db.create_import_run(source="apply_test", version="run2")
        ops = [
            import_diff.AddControl(
                key=("ASVS", "2.1", "V2.1.1"),
                document={
                    "name": "ASVS",
                    "section": "2.1",
                    "subsection": "",
                    "sectionID": "V2.1.1",
                    "description": "new ctrl",
                },
            )
        ]
        db.persist_staged_change_set(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json(ops),
            has_conflicts=False,
            staging_status="accepted",
        )
        res = import_apply.apply_changeset(run_id=run.id, dry_run=True)
        self.assertTrue(res.dry_run)
        self.assertEqual(
            self.collection.get_nodes(name="ASVS", section="2.1", sectionID="V2.1.1"),
            [],
        )
        cs = db.get_staged_change_set(run_id=run.id)
        self.assertEqual(cs.staging_status, "accepted")

    def test_apply_conflict_sets_apply_failed(self) -> None:
        self.collection.add_node(self._mk_std("current"))
        run = db.create_import_run(source="apply_test", version="run3")
        ops = [
            import_diff.ModifyControl(
                key=("ASVS", "1.1", "V1.1.1"),
                before={
                    "name": "ASVS",
                    "section": "1.1",
                    "subsection": "",
                    "sectionID": "V1.1.1",
                    "description": "stale-before",
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
        with self.assertRaises(import_apply.ApplyConflict):
            import_apply.apply_changeset(run_id=run.id, dry_run=False)
        cs = db.get_staged_change_set(run_id=run.id)
        self.assertEqual(cs.staging_status, "apply_failed")
        self.assertTrue(cs.apply_error)

