#!/usr/bin/env python3
"""
Phase 3 intermediate practical checkpoint verifier.

Validates apply readiness end-to-end through admin APIs:
- dry-run does not mutate
- apply mutates and marks applied
- re-apply is idempotent
- conflict returns 409 and marks apply_failed with apply_error
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ["INSECURE_REQUESTS"] = "1"
os.environ["NO_LOGIN"] = "1"
os.environ["ADMIN_IMPORTS_ENABLED"] = "1"

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_diff


@dataclass
class Report:
    dry_run_status: int
    apply_status: int
    apply_again_status: int
    conflict_status: int
    pass_status: bool


def _mk_modify_op(before_desc: str, after_desc: str) -> import_diff.ModifyControl:
    return import_diff.ModifyControl(
        key=("ASVS", "1.1", "V1.1.1"),
        before={
            "name": "ASVS",
            "section": "1.1",
            "subsection": "",
            "sectionID": "V1.1.1",
            "description": before_desc,
        },
        after={
            "name": "ASVS",
            "section": "1.1",
            "subsection": "",
            "sectionID": "V1.1.1",
            "description": after_desc,
        },
    )


def run() -> Report:
    app = create_app(mode="test")
    ctx = app.app_context()
    ctx.push()
    try:
        sqla.create_all()
        collection = db.Node_collection()
        collection.add_node(
            defs.Standard(
                name="ASVS",
                section="1.1",
                sectionID="V1.1.1",
                description="old",
            )
        )

        # Happy path run.
        run_ok = db.create_import_run(source="phase3_apply_cp", version="ok")
        db.persist_staged_change_set(
            run_id=run_ok.id,
            changeset_json=import_diff.change_set_to_json(
                [_mk_modify_op(before_desc="old", after_desc="new")]
            ),
            has_conflicts=False,
            staging_status="accepted",
        )

        with app.test_client() as c:
            dry_resp = c.post(f"/admin/imports/runs/{run_ok.id}/apply?dry_run=1")
            row = (
                sqla.session.query(db.Node)
                .filter(db.Node.name == "ASVS")
                .filter(db.Node.section == "1.1")
                .filter(db.Node.section_id == "V1.1.1")
                .first()
            )
            dry_ok = dry_resp.status_code == 200 and row and row.description == "old"

            apply_resp = c.post(f"/admin/imports/runs/{run_ok.id}/apply")
            row = (
                sqla.session.query(db.Node)
                .filter(db.Node.name == "ASVS")
                .filter(db.Node.section == "1.1")
                .filter(db.Node.section_id == "V1.1.1")
                .first()
            )
            cs = db.get_staged_change_set(run_id=run_ok.id)
            apply_ok = (
                apply_resp.status_code == 200
                and row
                and row.description == "new"
                and cs
                and cs.staging_status == "applied"
            )

            apply_again_resp = c.post(f"/admin/imports/runs/{run_ok.id}/apply")
            again_payload = apply_again_resp.get_json() if apply_again_resp.is_json else {}
            again_ok = apply_again_resp.status_code == 200 and bool(
                again_payload.get("already_applied")
            )

            # Conflict run.
            run_conflict = db.create_import_run(source="phase3_apply_cp", version="conflict")
            db.persist_staged_change_set(
                run_id=run_conflict.id,
                changeset_json=import_diff.change_set_to_json(
                    [_mk_modify_op(before_desc="stale-before", after_desc="latest")]
                ),
                has_conflicts=False,
                staging_status="accepted",
            )
            conflict_resp = c.post(f"/admin/imports/runs/{run_conflict.id}/apply")
            cs_conflict = db.get_staged_change_set(run_id=run_conflict.id)
            conflict_ok = (
                conflict_resp.status_code == 409
                and cs_conflict
                and cs_conflict.staging_status == "apply_failed"
                and bool(cs_conflict.apply_error)
            )

        pass_status = bool(dry_ok and apply_ok and again_ok and conflict_ok)
        return Report(
            dry_run_status=dry_resp.status_code,
            apply_status=apply_resp.status_code,
            apply_again_status=apply_again_resp.status_code,
            conflict_status=conflict_resp.status_code,
            pass_status=pass_status,
        )
    finally:
        sqla.session.remove()
        sqla.drop_all()
        ctx.pop()


def main() -> None:
    report = run()
    print("=== Phase 3 intermediate apply checkpoint ===")
    print(f"dry_run status: {report.dry_run_status}")
    print(f"apply status: {report.apply_status}")
    print(f"apply-again status: {report.apply_again_status}")
    print(f"conflict status: {report.conflict_status}")
    print(f"Phase3-Intermediate-Apply: {'PASS' if report.pass_status else 'FAIL'}")
    if not report.pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
