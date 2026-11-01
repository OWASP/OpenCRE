"""Scheduled refresh of approved external sites and YouTube channels (the ``external_sources`` job).

The job ticks daily like the others; each approved ``external_site`` is re-crawled only when its
own ``refresh_days`` have passed since its last successful ingest (kept as a runtime setting).
The job is off until an admin switches it on in the Schedules tab (``schedule_settings``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from application.utils.admin_panel import runtime_settings
from application.utils.comprehension import external


def last_run_key(spec_id: str) -> str:
    return "OIE_EXT_LAST_RUN_" + spec_id.upper().replace("-", "_")


def last_run(spec_id: str) -> Optional[datetime]:
    raw = runtime_settings.get_setting(last_run_key(spec_id))
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


YOUTUBE_REFRESH_MARGIN_DAYS = (
    5  # refresh this long before the 30-day storage limit, not at it
)


def refresh_interval_days(spec: external.ExternalSpec) -> int:
    if spec.kind == external.KIND_YOUTUBE:
        return max(1, spec.refresh_days - YOUTUBE_REFRESH_MARGIN_DAYS)
    return spec.refresh_days


def due_specs(
    specs: List[external.ExternalSpec], now: datetime
) -> List[external.ExternalSpec]:
    """Approved sites and YouTube channels never ingested, or last ingested ``refresh_days`` ago.

    YouTube channels are refreshed a few days early: stored API data may be kept at most 30 days.
    """
    out = []
    for spec in specs:
        if (
            spec.kind not in (external.KIND_SITE, external.KIND_YOUTUBE)
            or spec.status != external.STATUS_APPROVED
        ):
            continue
        done = last_run(spec.id)
        if done is None or now.replace(tzinfo=None) - done.replace(
            tzinfo=None
        ) >= timedelta(days=refresh_interval_days(spec)):
            out.append(spec)
    return out


def run(ctx: Any) -> Dict[str, Any]:
    """Ingest every due site or YouTube channel; returns ``{"due": n, "sites": {id: counts or error}}``."""
    from application.prompt_client import prompt_client
    from application.utils.comprehension import youtube_ingest
    from application.utils.comprehension.external_ingest import ingest_spec

    due = due_specs(
        external.load_specs(
            ctx.session, kinds=(external.KIND_SITE, external.KIND_YOUTUBE)
        ),
        ctx.now,
    )
    summary: Dict[str, Any] = {"due": len(due), "sites": {}}
    if not due:
        return summary
    embed = prompt_client.PromptHandler(
        ctx.collection, load_all_embeddings=False
    ).get_text_embeddings
    for spec in due:
        try:
            if spec.kind == external.KIND_YOUTUBE:
                counts = youtube_ingest.refresh_channel(
                    spec, ctx.collection, embed=embed, apply=not ctx.dry_run
                )
            else:
                counts = ingest_spec(
                    spec,
                    apply=not ctx.dry_run,
                    skip_unchanged=True,
                    database=ctx.collection,
                    embed=embed,
                )
            summary["sites"][spec.id] = counts
            if not ctx.dry_run:
                runtime_settings.set_setting(
                    last_run_key(spec.id), ctx.now.replace(tzinfo=None).isoformat()
                )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - one site failing must not block the others
            summary["sites"][spec.id] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return summary
