from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import uuid
from typing import Any, Dict, List, Optional

import yaml

from application import sqla  # type: ignore[attr-defined]
from application.database import db
from application.feature_flags import TRUE_VALUES
from application.utils import import_diff
from application.utils.admin_panel import config_catalog

REPOS_YAML = Path(__file__).resolve().parents[1] / "harvester" / "repos.yaml"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def agent_status() -> Dict[str, Any]:
    enabled = os.getenv("OWASP_AGENT_ENABLED", "").strip().lower() in TRUE_VALUES
    db_path = os.getenv("OWASP_AGENT_DB") or None
    pkg = importlib.util.find_spec("application.utils.owasp_agent") is not None
    return {
        "enabled": enabled,
        "db_configured": bool(db_path),
        "package_present": pkg,
        "demo_path": "/chatbot",
        "writes_cre_graph": False,
        "help_url": (
            "https://github.com/OWASP/OpenCRE/blob/main/"
            "application/utils/owasp_agent/README.md"
        ),
    }


def list_targets() -> List[Dict[str, Any]]:
    seed_targets_from_yaml_if_empty()
    rows = (
        sqla.session.query(db.IngestionTarget)
        .order_by(db.IngestionTarget.name.asc())
        .all()
    )
    return [_target_dict(t) for t in rows]


def seed_targets_from_yaml_if_empty() -> None:
    if sqla.session.query(db.IngestionTarget).first() is not None:
        return
    if not REPOS_YAML.is_file():
        return
    data = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8")) or {}
    for repo in data.get("repositories") or []:
        rid = str(repo.get("id") or "").strip()
        if not rid:
            continue
        t = db.IngestionTarget(
            id=rid,
            kind="oie_repo",
            name=rid,
            spec_json=json.dumps(repo),
            enabled=bool(repo.get("enabled", True)),
            created_at=_now(),
        )
        sqla.session.add(t)
    sqla.session.commit()


def add_target(
    *,
    target_id: str,
    kind: str,
    name: str,
    spec: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    if kind not in ("oie_repo", "import_source"):
        raise ValueError("kind must be oie_repo or import_source")
    existing = (
        sqla.session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.id == target_id)
        .first()
    )
    if existing:
        raise ValueError("target already exists")
    t = db.IngestionTarget(
        id=target_id,
        kind=kind,
        name=name or target_id,
        spec_json=json.dumps(spec or {}),
        enabled=enabled,
        created_at=_now(),
    )
    sqla.session.add(t)
    sqla.session.commit()
    return _target_dict(t)


def remove_target(target_id: str) -> bool:
    t = (
        sqla.session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.id == target_id)
        .first()
    )
    if not t:
        return False
    sqla.session.delete(t)
    sqla.session.commit()
    return True


def _target_dict(t: db.IngestionTarget) -> Dict[str, Any]:
    try:
        spec = json.loads(t.spec_json or "{}")
    except json.JSONDecodeError:
        spec = {}
    return {
        "id": t.id,
        "kind": t.kind,
        "name": t.name,
        "spec": spec,
        "enabled": bool(t.enabled),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def append_event(run_id: str, stage: str, status: str, detail: str = "") -> None:
    ev = db.AdminPipelineEvent(
        id=str(uuid.uuid4()),
        run_id=run_id,
        stage=stage,
        status=status,
        detail=detail or None,
        created_at=_now(),
    )
    sqla.session.add(ev)
    sqla.session.commit()


def start_ingestion(
    *,
    source: str,
    target_id: Optional[str] = None,
    run_oie: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    if not source:
        raise ValueError("source is required")
    target = None
    if target_id:
        target = (
            sqla.session.query(db.IngestionTarget)
            .filter(db.IngestionTarget.id == target_id)
            .first()
        )
        if not target:
            raise KeyError("target not found")
        if not target.enabled:
            raise ValueError("target is disabled")
        source = target.name or target.id

    run = db.create_import_run(source=source, version="admin-start")
    db.persist_staged_change_set(
        run_id=run.id,
        changeset_json=import_diff.change_set_to_json([]),
        staging_status="pending_review",
    )
    append_event(run.id, "queued", "ok", f"source={source}")
    oie: Optional[Dict[str, Any]] = None
    if run_oie:
        append_event(run.id, "oie", "started", "dry_run=%s" % dry_run)
        try:
            from application.utils.oie_orchestrator.pipeline import run_oie_pipeline

            cache = os.environ.get("CRE_CACHE_FILE", "")
            result = run_oie_pipeline(
                cache_file=cache,
                pipeline_run_id=run.id,
                dry_run=dry_run,
                stop_on_error=True,
            )
            oie = (
                result.to_dict() if hasattr(result, "to_dict") else {"raw": str(result)}
            )
            append_event(run.id, "oie", "ok", json.dumps(oie)[:2000])
        except Exception as exc:  # noqa: BLE001
            append_event(run.id, "oie", "error", str(exc))
            oie = {"error": str(exc)}
    else:
        append_event(
            run.id,
            "recorded",
            "ok",
            "Import run staged; apply via /admin/imports when ready",
        )
    return {"run_id": run.id, "source": source, "oie": oie}


def pipeline_snapshot() -> Dict[str, Any]:
    runs = db.list_import_runs(limit=50, offset=0)
    run_rows = []
    for r in runs:
        cs = db.get_staged_change_set(run_id=r.id)
        run_rows.append(
            {
                "id": r.id,
                "source": r.source,
                "version": r.version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "staging_status": cs.staging_status if cs else None,
            }
        )
    events = (
        sqla.session.query(db.AdminPipelineEvent)
        .order_by(db.AdminPipelineEvent.created_at.desc())
        .limit(200)
        .all()
    )
    oie_decisions: List[Dict[str, Any]] = []
    unconsumed = 0
    try:
        q = sqla.session.query(db.DecisionQueueItem)
        unconsumed = q.filter(db.DecisionQueueItem.consumed_at.is_(None)).count()
        for item in q.order_by(db.DecisionQueueItem.id.desc()).limit(20):
            oie_decisions.append(
                {
                    "id": item.id,
                    "status": item.status,
                    "source_label": item.source_label,
                    "pipeline_run_id": item.pipeline_run_id,
                    "consumed": item.consumed_at is not None,
                }
            )
    except Exception:  # noqa: BLE001
        unconsumed = 0
    return {
        "import_runs": run_rows,
        "events": [
            {
                "id": e.id,
                "run_id": e.run_id,
                "stage": e.stage,
                "status": e.status,
                "detail": e.detail,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "oie": {"unconsumed": unconsumed, "recent": oie_decisions},
    }


def edit_staged_mapping(
    run_id: str, op_index: int, after: Dict[str, Any]
) -> Dict[str, Any]:
    cs = db.get_staged_change_set(run_id=run_id)
    if not cs:
        raise KeyError("no staged change set")
    if cs.staging_status not in ("pending_review", "accepted"):
        raise ValueError("can only edit pending or accepted staged mappings")
    ops = json.loads(cs.changeset_json or "[]")
    if op_index < 0 or op_index >= len(ops):
        raise IndexError("op_index out of range")
    op = ops[op_index]
    if not isinstance(op, dict):
        raise ValueError("invalid op")
    op["after"] = after
    db.update_staged_change_set(run_id=run_id, changeset_json=json.dumps(ops))
    return {"run_id": run_id, "op_index": op_index, "after": after}


def drop_last_ingestion(source: str) -> Dict[str, Any]:
    run = db.get_latest_import_run(source)
    if not run:
        raise KeyError("no import run for source")
    cs = db.get_staged_change_set(run_id=run.id)
    if not cs:
        raise KeyError("no staged change set")
    if cs.staging_status == "applied":
        raise PermissionError(
            "last run is already applied; graph rollback is not implemented"
        )
    db.update_staged_change_set(run_id=run.id, staging_status="discarded")
    append_event(run.id, "dropped", "ok", f"source={source}")
    return {"run_id": run.id, "staging_status": "discarded"}


def config_get() -> List[Dict[str, Any]]:
    return config_catalog.present_config(os.environ)


def config_put(updates: Dict[str, Optional[str]]) -> Dict[str, Any]:
    applied, rejected = config_catalog.apply_updates(os.environ, updates)
    return {
        "applied": applied,
        "rejected": rejected,
        "config": config_get(),
        "needs_restart": True,
        "note": "HTTP cannot change process env; set vars in .env or Heroku config and restart.",
    }
