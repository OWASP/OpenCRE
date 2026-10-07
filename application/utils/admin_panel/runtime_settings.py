"""Durable admin runtime settings (DB) with optional process-env mirror."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from application import sqla
from application.database import db

FILING_KEY = "OIE_GRAPH_FILING_ENABLED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_setting(key: str) -> Optional[str]:
    """DB value if present; else None (caller falls back to env)."""
    try:
        row = (
            sqla.session.query(db.AdminRuntimeSetting)
            .filter(db.AdminRuntimeSetting.key == key)
            .first()
        )
    except Exception:
        sqla.session.rollback()
        return None
    if row is None:
        return None
    return str(row.value)


def filing_enabled() -> bool:
    """True when filing is on. Env wins when set; else DB; else default off."""
    env_raw = os.environ.get(FILING_KEY)
    if env_raw is not None and str(env_raw).strip() != "":
        return str(env_raw).strip().lower() in ("1", "true", "yes", "on")
    db_val = get_setting(FILING_KEY)
    if db_val is None:
        return False
    return db_val.strip().lower() in ("1", "true", "yes", "on")


def set_setting(key: str, value: str, *, actor: Optional[str] = None) -> None:
    """Upsert setting, append audit row, mirror into ``os.environ``."""
    now = _utcnow()
    row = (
        sqla.session.query(db.AdminRuntimeSetting)
        .filter(db.AdminRuntimeSetting.key == key)
        .first()
    )
    old = row.value if row is not None else None
    if row is None:
        row = db.AdminRuntimeSetting(
            key=key, value=value, updated_at=now, updated_by=actor
        )
        sqla.session.add(row)
    else:
        row.value = value
        row.updated_at = now
        row.updated_by = actor
    sqla.session.add(
        db.AdminRuntimeSettingAudit(
            key=key,
            old_value=old,
            new_value=value,
            actor=actor,
            created_at=now,
        )
    )
    sqla.session.commit()
    os.environ[key] = value


def hydrate_environ_from_db(environ: Optional[dict] = None) -> None:
    """Copy known DB settings into environ when unset (worker/web boot)."""
    target = environ if environ is not None else os.environ
    db_val = get_setting(FILING_KEY)
    if db_val is not None and not (target.get(FILING_KEY) or "").strip():
        target[FILING_KEY] = db_val
