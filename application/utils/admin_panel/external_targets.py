"""Registry of external knowledge sources (sites, YouTube) as ``IngestionTarget`` rows.

Link suggestions arrive as ``suggested`` + disabled rows; an admin accepts (approved + enabled) or
rejects (kept, disabled, so the same host is never suggested again). Nothing here crawls or fetches.
The shape of ``spec_json`` is the contract in ``application.utils.comprehension.external``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from application import sqla  # type: ignore[attr-defined]
from application.database import db
from application.utils.comprehension import external as ext
from application.utils.comprehension.link_suggestions import (
    candidate_id,
    registrable_host,
)

# Fields an admin may change when accepting or manually adding a source.
EDITABLE_FIELDS = (
    "name",
    "owner",
    "aliases",
    "weight",
    "refresh_days",
    "notes",
    "start_urls",
    "allow_prefixes",
    "max_pages",
    "max_depth",
    "channel_id",
    "playlist_id",
)
_MAX_FOUND_IN = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(session: Any) -> List[Any]:
    return (
        session.query(db.IngestionTarget)
        .filter(db.IngestionTarget.kind.in_(list(ext.KINDS)))
        .order_by(db.IngestionTarget.name.asc())
        .all()
    )


def _raw(row: Any) -> Dict[str, Any]:
    try:
        data = json.loads(row.spec_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _write(row: Any, spec: ext.ExternalSpec, score: Optional[float]) -> None:
    data = json.loads(ext.spec_to_json(spec))
    if score is not None:
        data["score"] = (
            score  # suggestion rank; not part of the contract, ignored by validate_spec
        )
    row.spec_json = json.dumps(data, sort_keys=True)


def external_dict(row: Any) -> Dict[str, Any]:
    raw = _raw(row)
    spec = ext.spec_from_target(row)
    return {
        "id": row.id,
        "kind": row.kind,
        "name": row.name,
        "enabled": bool(row.enabled),
        "status": (spec.status if spec else raw.get("status")) or "",
        "score": raw.get("score"),
        "spec": asdict(spec) if spec else raw,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def registered_hosts(session: Any = None) -> set:
    """Registrable hosts of every external target (any status, so rejected ones are never re-suggested)."""
    session = session or sqla.session
    hosts = set()
    for row in _rows(session):
        raw = _raw(row)
        for u in list(raw.get("start_urls") or []) + list(
            raw.get("allow_prefixes") or []
        ):
            h = urlparse(str(u)).hostname
            if h:
                hosts.add(registrable_host(h[4:] if h.startswith("www.") else h))
    return hosts


def _suggested_spec(cand: Dict[str, Any], cid: str) -> ext.ExternalSpec:
    if cand.get("kind") == "youtube":
        return ext.validate_spec(
            {
                "id": cid,
                "name": cand.get("name_guess") or cid,
                "kind": ext.KIND_YOUTUBE,
                "status": ext.STATUS_SUGGESTED,
                "channel_id": cand.get("channel_id") or "",
                "playlist_id": cand.get("playlist_id") or "",
                "found_in": cand.get("found_in") or [],
            }
        )
    return ext.validate_spec(
        {
            "id": cid,
            "name": cand.get("name_guess") or cid,
            "kind": ext.KIND_SITE,
            "status": ext.STATUS_SUGGESTED,
            "start_urls": [cand["url"]],
            "found_in": cand.get("found_in") or [],
            **{
                k: cand[k]
                for k in (
                    "allow_prefixes",
                    "max_pages",
                    "max_depth",
                    "refresh_days",
                    "notes",
                )
                if k in cand
            },
        }
    )


def _merge_found_in(
    old: List[Dict[str, Any]], new: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for f in list(old) + list(new):
        k = (f.get("repo"), f.get("file"), f.get("page"), f.get("url"))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out[:_MAX_FOUND_IN]


def upsert_suggestions(
    candidates: Iterable[Dict[str, Any]], session: Any = None
) -> Dict[str, List[str]]:
    """Store candidates as ``suggested`` disabled targets; never touches approved/rejected ones."""
    session = session or sqla.session
    created: List[str] = []
    merged: List[str] = []
    skipped: List[str] = []
    known_hosts = registered_hosts(session)
    for cand in candidates:
        try:
            cid = candidate_id(cand)
            row = session.query(db.IngestionTarget).filter_by(id=cid).first()
            if row is not None:
                spec = ext.spec_from_target(row)
                if spec is None or spec.status != ext.STATUS_SUGGESTED:
                    skipped.append(cid)
                    continue
                spec.found_in = _merge_found_in(spec.found_in, cand.get("found_in", []))
                old = _raw(row).get("score")
                score = max(float(old or 0), float(cand.get("score") or 0))
                _write(row, spec, score)
                merged.append(cid)
                continue
            if (
                cand.get("kind") != "youtube"
                and registrable_host(cand.get("host", "")) in known_hosts
            ):
                skipped.append(cid)
                continue
            spec = _suggested_spec(cand, cid)
        except (ValueError, KeyError):
            skipped.append(str(cand.get("host") or cand.get("url") or "?"))
            continue
        row = db.IngestionTarget(
            id=cid,
            kind=spec.kind,
            name=spec.name,
            enabled=False,
            created_at=_now(),
        )
        _write(row, spec, float(cand.get("score") or 0))
        session.add(row)
        created.append(cid)
        if spec.kind == ext.KIND_SITE:
            known_hosts.add(registrable_host(cand.get("host", "")))
    session.commit()
    return {"created": created, "merged": merged, "skipped": skipped}


def list_external(session: Any = None) -> List[Dict[str, Any]]:
    """All external targets (suggested, approved, rejected)."""
    return [external_dict(r) for r in _rows(session or sqla.session)]


def list_suggestions(session: Any = None) -> List[Dict[str, Any]]:
    out = [e for e in list_external(session) if e["status"] == ext.STATUS_SUGGESTED]
    out.sort(key=lambda e: (-(e["score"] or 0), e["id"]))
    return out


def _get(session: Any, target_id: str) -> Any:
    row = (
        session.query(db.IngestionTarget)
        .filter(
            db.IngestionTarget.id == target_id,
            db.IngestionTarget.kind.in_(list(ext.KINDS)),
        )
        .first()
    )
    if row is None:
        raise KeyError("external source not found")
    return row


def accept(
    target_id: str, overrides: Optional[Dict[str, Any]] = None, session: Any = None
) -> Dict[str, Any]:
    """Approve a source (optionally editing its spec first): status approved, enabled."""
    session = session or sqla.session
    row = _get(session, target_id)
    data = _raw(row)
    data.setdefault("id", row.id)
    data.setdefault("name", row.name)
    data.setdefault("kind", row.kind)
    for k, v in (overrides or {}).items():
        if k in EDITABLE_FIELDS:
            data[k] = v
    data["status"] = ext.STATUS_APPROVED
    spec = ext.validate_spec(data)
    row.name = spec.name
    row.enabled = True
    _write(row, spec, data.get("score"))
    session.commit()
    return external_dict(row)


def reject(target_id: str, session: Any = None) -> Dict[str, Any]:
    """Reject a source; the row stays (disabled) so it is never suggested again."""
    session = session or sqla.session
    row = _get(session, target_id)
    data = _raw(row)
    data.setdefault("id", row.id)
    data.setdefault("name", row.name)
    data.setdefault("kind", row.kind)
    data["status"] = ext.STATUS_REJECTED
    spec = ext.validate_spec(data)
    row.enabled = False
    _write(row, spec, data.get("score"))
    session.commit()
    return external_dict(row)


def add_manual(raw: Dict[str, Any], session: Any = None) -> Dict[str, Any]:
    """Add an admin-defined source straight away as approved + enabled."""
    session = session or sqla.session
    data = dict(raw or {})
    if not data.get("id"):
        start = (data.get("start_urls") or [""])[0]
        host = urlparse(start).hostname or ""
        data["id"] = (
            candidate_id({"kind": "site", "host": registrable_host(host)})
            if host
            else ""
        )
    data["status"] = ext.STATUS_APPROVED
    data.setdefault("kind", ext.KIND_SITE)
    spec = ext.validate_spec(data)
    if session.query(db.IngestionTarget).filter_by(id=spec.id).first() is not None:
        raise ValueError("target already exists")
    row = db.IngestionTarget(
        id=spec.id, kind=spec.kind, name=spec.name, enabled=True, created_at=_now()
    )
    _write(row, spec, None)
    session.add(row)
    session.commit()
    return external_dict(row)
