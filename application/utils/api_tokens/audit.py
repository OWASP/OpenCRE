"""Persist API-key request audit rows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import g, request

from application import sqla
from application.database import db

logger = logging.getLogger(__name__)


def record_api_key_audit(status_code: int) -> None:
    jti = getattr(g, "api_key_jti", None)
    if not jti:
        return
    try:
        row = db.ApiKeyAuditLog(
            id=db.generate_uuid(),
            jti=str(jti),
            method=request.method,
            path=(request.path or "")[:512],
            status_code=int(status_code),
            ip=(request.headers.get("X-Forwarded-For") or request.remote_addr or "")[
                :128
            ],
            user_agent=(request.headers.get("User-Agent") or "")[:512],
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        sqla.session.add(row)
        sqla.session.commit()
    except Exception:
        logger.exception("api key audit write failed jti=%s", jti)
        try:
            sqla.session.rollback()
        except Exception:
            pass


def list_audit_for_jti(jti: str, *, limit: int = 100) -> list[dict]:
    lim = max(1, min(int(limit), 500))
    rows = (
        sqla.session.query(db.ApiKeyAuditLog)
        .filter(db.ApiKeyAuditLog.jti == jti)
        .order_by(db.ApiKeyAuditLog.created_at.desc())
        .limit(lim)
        .all()
    )
    out = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "jti": row.jti,
                "method": row.method,
                "path": row.path,
                "status_code": row.status_code,
                "ip": row.ip,
                "user_agent": row.user_agent,
                "created_at": (
                    row.created_at.isoformat() + "Z" if row.created_at else None
                ),
            }
        )
    return out
