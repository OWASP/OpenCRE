#!/usr/bin/env python3
"""
Phase 2 Checkpoint 5 verifier (after Phase 2 Step 3).

Validates minimal admin APIs:
- GET /admin/imports/runs
- GET /admin/imports/runs/{run_id}
- GET /admin/imports/runs/{run_id}/changeset
"""

from __future__ import annotations

import os
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ["INSECURE_REQUESTS"] = "1"
os.environ["NO_LOGIN"] = "1"
os.environ["ADMIN_IMPORTS_ENABLED"] = "1"

from application import create_app, sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_pipeline
from application.utils.external_project_parsers import base_parser_defs


def _seed_run(app, *, source: str, version: str, desc: str) -> str:
    with app.app_context():
        sqla.create_all()
        collection = db.Node_collection()
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
                source="checkpoint_phase2_cp5",
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
            collection=collection,
            import_run_id=run.id,
            import_source=run.source,
        )
        return run.id


def main() -> None:
    _db_path = tempfile.mkstemp(prefix="opencre_phase2_cp5_", suffix=".sqlite")[1]
    app = create_app(mode="test")

    run1 = _seed_run(app, source="checkpoint_phase2_cp5", version="run1", desc="one")
    run2 = _seed_run(app, source="checkpoint_phase2_cp5", version="run2", desc="one")

    with app.test_client() as c:
        r = c.get("/admin/imports/runs?source=checkpoint_phase2_cp5")
        assert r.status_code == 200, r.data
        runs = r.get_json()["runs"]
        ids = {x["id"] for x in runs}
        assert run1 in ids and run2 in ids, ids

        r = c.get(f"/admin/imports/runs/{run2}")
        assert r.status_code == 200, r.data
        detail = r.get_json()
        assert detail["id"] == run2

        r = c.get(f"/admin/imports/runs/{run2}/changeset")
        assert r.status_code == 200, r.data
        cs = r.get_json()
        assert cs["staging_status"] == "pending_review"
        assert cs["changeset"] == [], cs["changeset"]

    print("=== Phase 2 Checkpoint 5 verification ===")
    print("Phase2-Checkpoint5: PASS")


if __name__ == "__main__":
    main()

