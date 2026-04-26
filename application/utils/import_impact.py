"""
Phase 3 (v3) — impact summary from staged change sets (read-only).
"""

from __future__ import annotations

from typing import Any, Dict

from application.database import db
from application.utils import import_diff


def impact_summary_for_run(
    run_id: str, collection: db.Node_collection
) -> Dict[str, Any]:
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        return {
            "run_id": run_id,
            "operation_count": 0,
            "impacted_standard_names": [],
            "impacted_cre_external_ids": [],
        }
    return impact_summary_from_changeset_json(
        cs.changeset_json or "[]", collection=collection, run_id=run_id
    )


def impact_summary_from_changeset_json(
    changeset_json: str,
    *,
    collection: db.Node_collection,
    run_id: str | None = None,
) -> Dict[str, Any]:
    ops = import_diff.change_set_from_json(changeset_json or "[]")
    names = sorted(import_diff.impacted_standard_names_from_ops(ops))
    cre_ids = sorted(
        import_diff.impacted_cre_external_ids_for_standards(collection, set(names))
    )
    out: Dict[str, Any] = {
        "operation_count": len(ops),
        "impacted_standard_names": names,
        "impacted_cre_external_ids": cre_ids,
    }
    if run_id is not None:
        out["run_id"] = run_id
    return out
