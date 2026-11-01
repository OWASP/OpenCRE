"""Admin-editable schedule for OIE jobs (interval and on/off), stored as runtime settings.

The scheduler process and the web process are separate, so the DB value is the source of
truth (the env mirror ``set_setting`` writes only exists in the web process).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from application.utils.admin_panel import runtime_settings

MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 7 * 24 * 60  # one week


def _key(job: str, field: str) -> str:
    return f"OIE_JOB_{job.upper()}_{field}"


def effective_interval_minutes(job: str, default: int) -> int:
    """Interval the scheduler should use: the admin override when valid, else ``default``."""
    raw = runtime_settings.get_setting(_key(job, "INTERVAL_MINUTES"))
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        return default
    if not MIN_INTERVAL_MINUTES <= value <= MAX_INTERVAL_MINUTES:
        return default
    return value


#: Jobs that crawl third-party sites stay off until an admin switches them on.
DEFAULT_OFF = frozenset({"external_sources"})


def job_enabled(job: str) -> bool:
    """Jobs run unless an admin switched them off; ``DEFAULT_OFF`` jobs only once switched on."""
    raw = runtime_settings.get_setting(_key(job, "ENABLED"))
    if raw is None:
        return job not in DEFAULT_OFF
    return raw.strip().lower() in ("1", "true", "yes", "on")


def validate_update(
    job: str, interval_minutes: Optional[Any], enabled: Optional[Any]
) -> Dict[str, Any]:
    """Normalise an update request; raises ValueError with a user-facing message."""
    from application.utils.oie_scheduler.jobs import JOBS

    if job not in JOBS:
        raise ValueError(f"unknown job {job!r}; expected one of {sorted(JOBS)}")
    out: Dict[str, Any] = {}
    if interval_minutes is not None:
        if isinstance(interval_minutes, bool) or not isinstance(
            interval_minutes, (int, str)
        ):
            raise ValueError("interval_minutes must be an integer")
        try:
            value = int(interval_minutes)
        except ValueError:
            raise ValueError("interval_minutes must be an integer") from None
        if not MIN_INTERVAL_MINUTES <= value <= MAX_INTERVAL_MINUTES:
            raise ValueError(
                f"interval_minutes must be between {MIN_INTERVAL_MINUTES} and {MAX_INTERVAL_MINUTES}"
            )
        out["interval_minutes"] = value
    if enabled is not None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be true or false")
        out["enabled"] = enabled
    if not out:
        raise ValueError("interval_minutes or enabled required")
    return out


def apply_update(job: str, update: Dict[str, Any], *, actor: Optional[str]) -> None:
    if "interval_minutes" in update:
        runtime_settings.set_setting(
            _key(job, "INTERVAL_MINUTES"), str(update["interval_minutes"]), actor=actor
        )
    if "enabled" in update:
        runtime_settings.set_setting(
            _key(job, "ENABLED"), "1" if update["enabled"] else "0", actor=actor
        )


def list_schedule(session: Any = None) -> List[Dict[str, Any]]:
    """Every job with its default and effective schedule, last run and next expected slot."""
    from application.utils.oie_scheduler import run_log
    from application.utils.oie_scheduler.jobs import JOB_ORDER, JOBS

    now = run_log.utcnow()
    rows: List[Dict[str, Any]] = []
    for name in JOB_ORDER:
        spec = JOBS[name]
        interval = effective_interval_minutes(name, spec.interval_minutes)
        enabled = job_enabled(name)
        last: Optional[Dict[str, Any]] = None
        if session is not None:
            try:
                runs = run_log.list_runs(session, job=name, limit=1)
                last = run_log.run_to_dict(runs[0]) if runs else None
            except (
                Exception
            ):  # noqa: BLE001 -- schedule view must render without run history
                session.rollback()
        rows.append(
            {
                "job": name,
                "description": spec.description,
                "default_interval_minutes": spec.interval_minutes,
                "interval_minutes": interval,
                "overridden": interval != spec.interval_minutes,
                "enabled": enabled,
                "next_expected": (
                    run_log.expected_next(interval, now).isoformat()
                    if enabled
                    else None
                ),
                "last_run": last,
            }
        )
    return rows
