#!/usr/bin/env python3
"""
Checkpoint 3 verification (Steps 6, 7, 8).

Validates:
- Step 6: import runs are persisted and ordered.
- Step 7: structured change-set is generated and round-trips JSON.
- Step 8: manual edits in main graph are detected as conflicts.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from application import sqla
from application.cmd import cre_main
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_diff


@dataclass
class Checkpoint3Report:
    import_runs_created: int
    latest_run_version: str
    added: int
    removed: int
    modified: int
    change_set_ops: int
    conflict_ops: int
    pass_status: bool


def _seed_baseline(collection: db.Node_collection) -> List[defs.Standard]:
    baseline = [
        defs.Standard(
            name="ASVS", section="1.1", sectionID="V1.1.1", description="baseline one"
        ),
        defs.Standard(
            name="ASVS", section="1.2", sectionID="V1.1.2", description="baseline two"
        ),
    ]
    for std in baseline:
        collection.add_node(std)
    return baseline


def _incoming_import_snapshot() -> List[defs.Standard]:
    return [
        defs.Standard(
            name="ASVS", section="1.1", sectionID="V1.1.1", description="imported update"
        ),
        defs.Standard(
            name="ASVS", section="1.3", sectionID="V1.1.3", description="new control"
        ),
    ]


def _with_manual_edit(baseline: List[defs.Standard]) -> List[defs.Standard]:
    current = [
        defs.Standard(
            name=s.name,
            section=s.section,
            sectionID=s.sectionID,
            subsection=s.subsection,
            description=s.description,
        )
        for s in baseline
    ]
    # Simulate a manual edit in the main graph on a key that import wants to modify.
    current[0].description = "manual main-graph edit"
    return current


def run_checkpoint_3_verify(db_path: str, simulate_manual_edit: bool = True) -> Checkpoint3Report:
    collection = cre_main.db_connect(path=db_path)
    sqla.create_all()

    db.create_import_run(source="checkpoint3", version="run1")
    baseline = _seed_baseline(collection)

    db.create_import_run(source="checkpoint3", version="run2")
    latest = db.get_latest_import_run("checkpoint3")

    incoming = _incoming_import_snapshot()
    diff = import_diff.diff_standards(previous=baseline, new=incoming)
    ops = import_diff.diff_to_change_set(diff)
    encoded = import_diff.change_set_to_json(ops)
    decoded_ops = import_diff.change_set_from_json(encoded)

    main_graph_snapshot = (
        _with_manual_edit(baseline) if simulate_manual_edit else list(baseline)
    )
    manual_keys = import_diff.detect_manual_edit_keys(
        baseline=baseline,
        current_main_graph=main_graph_snapshot,
    )
    conflicts = import_diff.detect_conflicts(decoded_ops, manual_keys)

    pass_status = (
        latest is not None
        and latest.version == "run2"
        and len(diff.added) == 1
        and len(diff.removed) == 1
        and len(diff.modified) == 1
        and len(decoded_ops) == 3
        and ((len(conflicts) > 0) if simulate_manual_edit else (len(conflicts) == 0))
    )

    return Checkpoint3Report(
        import_runs_created=2,
        latest_run_version=latest.version if latest else "",
        added=len(diff.added),
        removed=len(diff.removed),
        modified=len(diff.modified),
        change_set_ops=len(decoded_ops),
        conflict_ops=len(conflicts),
        pass_status=pass_status,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Checkpoint 3 verification for Steps 6/7/8."
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite DB path. Default: temporary file.",
    )
    parser.add_argument(
        "--no-manual-edit",
        action="store_true",
        help="Skip simulated manual main-graph edits (expect zero conflicts).",
    )
    args = parser.parse_args()

    db_path = args.db or tempfile.mkstemp(
        prefix="opencre_checkpoint3_", suffix=".sqlite"
    )[1]
    report = run_checkpoint_3_verify(
        db_path=db_path, simulate_manual_edit=not args.no_manual_edit
    )

    print("=== Checkpoint 3 verification ===")
    print(f"DB: {db_path}")
    print(f"Import runs created: {report.import_runs_created}")
    print(f"Latest run version: {report.latest_run_version}")
    print(f"Diff counts: added={report.added} removed={report.removed} modified={report.modified}")
    print(f"Change-set operations: {report.change_set_ops}")
    print(f"Conflict operations: {report.conflict_ops}")
    print(f"Checkpoint3: {'PASS' if report.pass_status else 'FAIL'}")

    if not report.pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

