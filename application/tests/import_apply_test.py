"""Test import_apply with nodes that have different subsections."""

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_apply, import_diff


class TestImportApplySubsectionIdentity(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.app_context.pop()

    def _stage(self, ops: list) -> str:
        run = db.create_import_run(source="import_apply_test")
        cs = db.StagedChangeSet(
            run_id=run.id,
            changeset_json=import_diff.change_set_to_json(ops),
            has_conflicts=False,
            staging_status="accepted",
            created_at=datetime.now(timezone.utc),
        )
        sqla.session.add(cs)
        sqla.session.commit()
        return run.id

    def test_modify_targets_the_matching_subsection_not_a_sibling(self) -> None:
        # Two ASVS entries share name/section/sectionID and differ only by
        # subsection -- exactly the case the DB's uq_node constraint allows.
        overview = db.Node(
            name="ASVS",
            section="V2: Authentication",
            subsection="",
            section_id="V2.1.1",
            description="Overview text",
            ntype=defs.Credoctypes.Standard.value,
            tags="",
            version="",
            link="",
        )
        password_rule = db.Node(
            name="ASVS",
            section="V2: Authentication",
            subsection="Password Security",
            section_id="V2.1.1",
            description="Old password rules",
            ntype=defs.Credoctypes.Standard.value,
            tags="",
            version="",
            link="",
        )
        sqla.session.add(overview)
        sqla.session.add(password_rule)
        sqla.session.commit()

        op = import_diff.ModifyControl(
            key=("ASVS", "V2: Authentication", "V2.1.1"),
            before={
                "name": "ASVS",
                "section": "V2: Authentication",
                "subsection": "Password Security",
                "sectionID": "V2.1.1",
                "description": "Old password rules",
            },
            after={
                "name": "ASVS",
                "section": "V2: Authentication",
                "subsection": "Password Security",
                "sectionID": "V2.1.1",
                "description": "New password rules",
            },
        )
        run_id = self._stage([op])

        result = import_apply.apply_changeset(run_id=run_id)

        self.assertEqual(result.applied_ops, 1)
        self.assertEqual(result.skipped_ops, 0)

        sqla.session.refresh(overview)
        sqla.session.refresh(password_rule)
        self.assertEqual(password_rule.description, "New password rules")
        # The sibling entry that only differs by subsection must be untouched.
        self.assertEqual(overview.description, "Overview text")

    def test_modify_finds_node_with_null_subsection(self) -> None:
        # Regression: blank input subsection must match a DB NULL subsection.
        null_subsection_node = db.Node(
            name="ASVS",
            section="V2: Authentication",
            subsection=None,
            section_id="V2.1.1",
            description="Overview text",
            ntype=defs.Credoctypes.Standard.value,
            tags="",
            version="",
            link="",
        )
        sqla.session.add(null_subsection_node)
        sqla.session.commit()

        op = import_diff.ModifyControl(
            key=("ASVS", "V2: Authentication", "V2.1.1"),
            before={
                "name": "ASVS",
                "section": "V2: Authentication",
                "subsection": "",
                "sectionID": "V2.1.1",
                "description": "Overview text",
            },
            after={
                "name": "ASVS",
                "section": "V2: Authentication",
                "subsection": "",
                "sectionID": "V2.1.1",
                "description": "Updated overview text",
            },
        )
        run_id = self._stage([op])

        result = import_apply.apply_changeset(run_id=run_id)

        self.assertEqual(result.applied_ops, 1)
        sqla.session.refresh(null_subsection_node)
        self.assertEqual(
            null_subsection_node.description,
            "Updated overview text",
        )
