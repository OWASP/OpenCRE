#!/usr/bin/env python3
"""
Phase 2 Checkpoint 4 verifier (after Phase 2 Steps 1 & 2).

Validates:
- Standard snapshots are persisted per import run.
- Re-import of identical content yields an empty/trivial change set.
- staging_status defaults to pending_review.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from application import create_app
from application import sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_diff, import_pipeline
from application.utils.external_project_parsers import base_parser_defs


@dataclass
class Report:
    snapshots_first: int
    snapshots_second: int
    changeset_ops_second: int
    staging_status_second: str
    pass_status: bool


def _parse_result_for(std: defs.Standard) -> base_parser_defs.ParseResult:
    return base_parser_defs.ParseResult(
        results={std.name: [std]},
        calculate_gap_analysis=False,
        calculate_embeddings=False,
    )


def run(db_path: str) -> Report:
    app = create_app(mode="test")
    ctx = app.app_context()
    ctx.push()
    try:
        sqla.create_all()

        collection = db.Node_collection()

        std = defs.Standard(
            name="ASVS",
            section="1.1",
            sectionID="V1.1.1",
            tags=base_parser_defs.build_tags(
                family=base_parser_defs.Family.STANDARD,
                subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
                audience=base_parser_defs.Audience.DEVELOPER,
                maturity=base_parser_defs.Maturity.STABLE,
                source="checkpoint_phase2",
                extra=[],
            ),
        )

        run1 = db.create_import_run(source="checkpoint_phase2", version="run1")
        import_pipeline.apply_parse_result(
            parse_result=_parse_result_for(std),
            collection=collection,
            db_connection_str=db_path,
            import_run_id=run1.id,
            import_source=run1.source,
        )
        snap1 = db.get_standard_snapshot(run_id=run1.id, standard_name="ASVS")

        run2 = db.create_import_run(source="checkpoint_phase2", version="run2")
        import_pipeline.apply_parse_result(
            parse_result=_parse_result_for(std),
            collection=collection,
            db_connection_str=db_path,
            import_run_id=run2.id,
            import_source=run2.source,
        )
        snap2 = db.get_standard_snapshot(run_id=run2.id, standard_name="ASVS")
        cs2 = db.get_staged_change_set(run_id=run2.id)

        ops = import_diff.change_set_from_json(cs2.changeset_json if cs2 else "[]")
        pass_status = (
            snap1 is not None
            and snap2 is not None
            and cs2 is not None
            and len(ops) == 0
            and cs2.staging_status == "pending_review"
        )
        return Report(
            snapshots_first=1 if snap1 else 0,
            snapshots_second=1 if snap2 else 0,
            changeset_ops_second=len(ops),
            staging_status_second=cs2.staging_status if cs2 else "",
            pass_status=pass_status,
        )
    finally:
        sqla.session.remove()
        sqla.drop_all()
        ctx.pop()


def main() -> None:
    db_path = tempfile.mkstemp(prefix="opencre_phase2_cp4_", suffix=".sqlite")[1]
    report = run(db_path=db_path)
    print("=== Phase 2 Checkpoint 4 verification ===")
    print(f"DB: {db_path}")
    print(f"Snapshots persisted (run1): {report.snapshots_first}")
    print(f"Snapshots persisted (run2): {report.snapshots_second}")
    print(f"Run2 changeset ops: {report.changeset_ops_second}")
    print(f"Run2 staging_status: {report.staging_status_second}")
    print(f"Phase2-Checkpoint4: {'PASS' if report.pass_status else 'FAIL'}")
    if not report.pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

