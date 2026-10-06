"""
Phase 3 (v3) — impact summary from staged change sets (read-only).
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

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
    empty_key_ops = sum(
        1 for op in ops if not import_diff.standard_name_from_op_key(op)
    )
    names = sorted(import_diff.impacted_standard_names_from_ops(ops))
    warnings: list[str] = []
    if empty_key_ops:
        msg = f"Skipped {empty_key_ops} operation(s) with empty standard keys"
        logger.warning("Impact run_id=%s: %s", run_id, msg)
        warnings.append(msg)
    cre_ids: list[str] = []
    try:
        cre_ids = sorted(
            import_diff.impacted_cre_external_ids_for_standards(collection, set(names))
        )
    except Exception as e:
        logger.exception(
            "Impact CRE lookup failed run_id=%s names=%s", run_id, names
        )
        warnings.append(f"CRE impact lookup failed: {e}")
    logger.info(
        "Impact summary run_id=%s ops=%s standards=%s cres=%s warnings=%s",
        run_id,
        len(ops),
        names,
        cre_ids,
        warnings,
    )
    out: Dict[str, Any] = {
        "operation_count": len(ops),
        "impacted_standard_names": names,
        "impacted_cre_external_ids": cre_ids,
    }
    if warnings:
        out["warnings"] = warnings
    if run_id is not None:
        out["run_id"] = run_id
    return out
