"""
Phase 3 (v3) apply engine for staged change sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from application import sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils import import_diff


class ApplyError(Exception):
    pass


class ApplyConflict(ApplyError):
    pass


@dataclass
class ApplyResult:
    run_id: str
    dry_run: bool
    staging_status: str
    touched_keys: List[Tuple[str, str, str]]
    applied_ops: int
    skipped_ops: int
    already_applied: bool = False


def _doc_from_node(n: db.Node) -> Dict[str, Any]:
    return {
        "name": n.name or "",
        "section": n.section or "",
        "subsection": n.subsection or "",
        "sectionID": n.section_id or "",
        "description": n.description or "",
    }


def _same_doc(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    keys = ("name", "section", "subsection", "sectionID", "description")
    return all((a.get(k) or "") == (b.get(k) or "") for k in keys)


def _get_node_for_key(key: Tuple[str, str, str]) -> db.Node | None:
    name, section, section_id = key
    q = sqla.session.query(db.Node).filter(db.Node.name == name)
    q = q.filter(db.Node.section == (section or ""))
    q = q.filter(db.Node.section_id == (section_id or ""))
    q = q.filter(db.Node.ntype == defs.Credoctypes.Standard.value)
    return q.first()


def apply_changeset(
    *,
    run_id: str,
    dry_run: bool = False,
    db_connection_str: str = "",
    run_post_apply_effects: bool = False,
) -> ApplyResult:
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        raise ApplyError(f"No staged change set for run_id={run_id}")

    if cs.staging_status == "discarded":
        raise ApplyError(f"Run {run_id} was discarded and cannot be applied")

    if cs.has_conflicts:
        raise ApplyConflict(f"Run {run_id} has conflicts and cannot be applied")

    if not dry_run and cs.staging_status == "applied":
        return ApplyResult(
            run_id=run_id,
            dry_run=False,
            staging_status="applied",
            touched_keys=[],
            applied_ops=0,
            skipped_ops=0,
            already_applied=True,
        )

    if not dry_run and cs.staging_status not in ("accepted",):
        raise ApplyError(
            f"Run {run_id} must be in accepted status before apply (current={cs.staging_status})"
        )

    ops = import_diff.change_set_from_json(cs.changeset_json or "[]")
    touched: List[Tuple[str, str, str]] = []
    applied = 0
    skipped = 0

    try:
        for op in ops:
            key = tuple(op.key)  # type: ignore[arg-type]
            touched.append(key)  # type: ignore[arg-type]
            current = _get_node_for_key(key)  # type: ignore[arg-type]

            if isinstance(op, import_diff.AddControl):
                incoming = op.document or {}
                if current:
                    if _same_doc(_doc_from_node(current), incoming):
                        skipped += 1
                        continue
                    raise ApplyConflict(
                        f"Add conflict for key={key}: node already exists"
                    )
                if not dry_run:
                    sqla.session.add(
                        db.Node(
                            name=(incoming.get("name") or key[0]),
                            section=(incoming.get("section") or ""),
                            subsection=(incoming.get("subsection") or ""),
                            section_id=(incoming.get("sectionID") or ""),
                            description=(incoming.get("description") or ""),
                            ntype=defs.Credoctypes.Standard.value,
                            tags="",
                            version="",
                            link="",
                            metadata_json={},
                        )
                    )
                applied += 1

            elif isinstance(op, import_diff.RemoveControl):
                expected = op.document or {}
                if not current:
                    raise ApplyConflict(f"Remove conflict for key={key}: node missing")
                if not _same_doc(_doc_from_node(current), expected):
                    raise ApplyConflict(f"Remove conflict for key={key}: node changed")
                if not dry_run:
                    sqla.session.delete(current)
                applied += 1

            elif isinstance(op, import_diff.ModifyControl):
                before = op.before or {}
                after = op.after or {}
                if not current:
                    raise ApplyConflict(f"Modify conflict for key={key}: node missing")
                if not _same_doc(_doc_from_node(current), before):
                    raise ApplyConflict(f"Modify conflict for key={key}: stale before")
                if _same_doc(before, after):
                    skipped += 1
                    continue
                if not dry_run:
                    current.name = after.get("name") or current.name
                    current.section = after.get("section") or ""
                    current.subsection = after.get("subsection") or ""
                    current.section_id = after.get("sectionID") or ""
                    current.description = after.get("description") or ""
                    sqla.session.add(current)
                applied += 1

        if dry_run:
            sqla.session.rollback()
            return ApplyResult(
                run_id=run_id,
                dry_run=True,
                staging_status=cs.staging_status,
                touched_keys=touched,
                applied_ops=applied,
                skipped_ops=skipped,
            )

        cs.staging_status = "applied"
        cs.apply_error = None
        sqla.session.add(cs)
        sqla.session.commit()
        if run_post_apply_effects and db_connection_str and touched:
            from application.utils import import_post_apply

            import_post_apply.run_post_apply(
                db_connection_str=db_connection_str,
                touched_standard_names=[k[0] for k in touched],
            )
        return ApplyResult(
            run_id=run_id,
            dry_run=False,
            staging_status="applied",
            touched_keys=touched,
            applied_ops=applied,
            skipped_ops=skipped,
        )
    except Exception as ex:
        sqla.session.rollback()
        if not dry_run:
            db.update_staged_change_set(
                run_id=run_id, staging_status="apply_failed", apply_error=str(ex)
            )
        raise
