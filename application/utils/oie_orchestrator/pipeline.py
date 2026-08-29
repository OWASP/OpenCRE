"""OIE orchestrator — A → B → C for one ``pipeline_run_id``.

Production sequencing: run each stage, wait for process/library return,
then start the next. Modules communicate only through DB tables:

  A writes ``harvest_input`` → B writes ``knowledge_queue`` → C writes
  ``decision_queue`` / stamps ``consumed_at``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Outcome of one orchestrator stage (module A, B, or C)."""

    name: str
    status: str  # ok | skipped | error
    detail: str
    summary: Optional[Dict[str, Any]] = None


@dataclass
class OrchestratorResult:
    """Full A→B→C run summary (JSON-serializable)."""

    run_id: str
    dry_run: bool
    stages: List[StageResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "stages": [asdict(s) for s in self.stages],
            "ok": all(s.status in ("ok", "skipped", "degraded") for s in self.stages),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _summary_dict(summary: Any) -> Dict[str, Any]:
    if hasattr(summary, "to_json"):
        return json.loads(summary.to_json())
    if hasattr(summary, "__dict__"):
        return dict(summary.__dict__)
    return {"raw": str(summary)}


def _stage_status_from_summary(summary: Any) -> str:
    """Map module RunSummary.status to orchestrator stage status.

    Module C currently always reports ``degraded: N decided without the safety
    path`` behind ``NullSafetyGuard`` — that is declared, not a hard failure, so
    the stage is ``degraded`` (pipeline may continue; Module D must refuse while
    unevaluated > 0). Other ``degraded`` values (A/B partial runs, C row errors)
    map to ``error`` so ``stop_on_error`` can halt.
    """
    raw = getattr(summary, "status", None)
    if isinstance(summary, dict):
        raw = summary.get("status", raw)
    text = str(raw or "ok")
    if text == "ok":
        return "ok"
    if text.startswith("degraded") and "without the safety path" in text:
        # Pure safety-path gap, no errored rows mixed in.
        if "errored" not in text:
            return "degraded"
    return "error"


def _connect(cache_file: str) -> Any:
    from application import sqla
    from application.cmd.cre_main import db_connect

    db_connect(cache_file)
    return sqla.session


def _stage_module_a(
    run_id: str,
    cache_file: str,
    *,
    skip: bool,
    dry_run: bool,
    sync_repos: bool,
    run_harvester_fn: Optional[Callable[..., Any]] = None,
) -> StageResult:
    if skip:
        return StageResult(
            name="module_a_harvester",
            status="skipped",
            detail="skip_a=True; harvester not invoked",
        )

    fn = run_harvester_fn
    if fn is None:
        from application.utils.harvester.pipeline import run_harvester

        fn = run_harvester

    try:
        session = _connect(cache_file)
        summary = fn(
            session,
            run_id,
            dry_run=dry_run,
            sync_repos=sync_repos,
        )
        return StageResult(
            name="module_a_harvester",
            status=_stage_status_from_summary(summary),
            detail=f"run_harvester completed for run_id={run_id!r}",
            summary=_summary_dict(summary),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module A stage failed")
        return StageResult(
            name="module_a_harvester",
            status="error",
            detail=f"run_harvester failed: {exc}",
        )


def _stage_module_b(
    run_id: str,
    cache_file: str,
    *,
    skip: bool,
    dry_run: bool,
    run_noise_filter_fn: Optional[Callable[..., Any]] = None,
) -> StageResult:
    if skip:
        return StageResult(
            name="module_b_noise_filter",
            status="skipped",
            detail="skip_b=True; noise filter not invoked",
        )

    fn = run_noise_filter_fn
    if fn is None:
        from application.utils.noise_filter.pipeline import run_noise_filter

        fn = run_noise_filter

    try:
        session = _connect(cache_file)
        summary = fn(session, run_id, dry_run=dry_run)
        return StageResult(
            name="module_b_noise_filter",
            status=_stage_status_from_summary(summary),
            detail=f"run_noise_filter completed for run_id={run_id!r}",
            summary=_summary_dict(summary),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module B stage failed")
        return StageResult(
            name="module_b_noise_filter",
            status="error",
            detail=f"run_noise_filter failed: {exc}",
        )


def _stage_module_c(
    run_id: str,
    cache_file: str,
    *,
    skip: bool,
    dry_run: bool,
    run_librarian_queue_fn: Optional[Callable[..., Any]] = None,
) -> StageResult:
    if skip:
        return StageResult(
            name="module_c_librarian",
            status="skipped",
            detail="skip_c=True; librarian not invoked",
        )

    try:
        if run_librarian_queue_fn is not None:
            # Injected path (tests / hermetic smoke): caller owns session + sink.
            summary = run_librarian_queue_fn(run_id, dry_run=dry_run)
        else:
            from application.cmd.cre_main import db_connect
            from application.utils.librarian.config_loader import load_config
            from application.utils.librarian.envelope_sink import (
                DbEnvelopeSink,
                NullEnvelopeSink,
            )
            from application.utils.librarian.factory import build_components
            from application.utils.librarian.queue_runner import run_librarian_queue

            cfg = load_config()
            database = db_connect(path=cache_file)
            components = build_components(database, config=cfg)
            sink = (
                NullEnvelopeSink()
                if dry_run
                else DbEnvelopeSink(database.session, run_id)
            )
            summary = run_librarian_queue(
                database.session,
                run_id,
                components,
                cfg,
                at=datetime.now(timezone.utc),
                sink=sink,
                dry_run=dry_run,
            )

        return StageResult(
            name="module_c_librarian",
            status=_stage_status_from_summary(summary),
            detail=f"run_librarian_queue completed for run_id={run_id!r}",
            summary=(
                _summary_dict(summary) if not isinstance(summary, dict) else summary
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module C stage failed")
        return StageResult(
            name="module_c_librarian",
            status="error",
            detail=f"run_librarian_queue failed: {exc}",
        )


def run_oie_pipeline(
    *,
    cache_file: str,
    pipeline_run_id: Optional[str] = None,
    skip_a: bool = False,
    skip_b: bool = False,
    skip_c: bool = False,
    dry_run: bool = False,
    sync_repos: bool = True,
    stop_on_error: bool = True,
    run_harvester_fn: Optional[Callable[..., Any]] = None,
    run_noise_filter_fn: Optional[Callable[..., Any]] = None,
    run_librarian_queue_fn: Optional[Callable[..., Any]] = None,
) -> OrchestratorResult:
    """
    Run A→B→C for one ``pipeline_run_id``.

    Defaults run all stages for real (not dry-run). Inject callables in tests.
    When ``stop_on_error`` is True (default), later stages are skipped after
    an earlier stage returns ``error``.
    """
    run_id = (pipeline_run_id or "").strip() or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    result = OrchestratorResult(run_id=run_id, dry_run=dry_run)

    a = _stage_module_a(
        run_id,
        cache_file,
        skip=skip_a,
        dry_run=dry_run,
        sync_repos=sync_repos,
        run_harvester_fn=run_harvester_fn,
    )
    result.stages.append(a)
    if stop_on_error and a.status == "error":
        return result

    b = _stage_module_b(
        run_id,
        cache_file,
        skip=skip_b,
        dry_run=dry_run,
        run_noise_filter_fn=run_noise_filter_fn,
    )
    result.stages.append(b)
    if stop_on_error and b.status == "error":
        return result

    c = _stage_module_c(
        run_id,
        cache_file,
        skip=skip_c,
        dry_run=dry_run,
        run_librarian_queue_fn=run_librarian_queue_fn,
    )
    result.stages.append(c)
    return result


# Back-compat alias used by the draft PoC script name.
run_oie_demo_pipeline = run_oie_pipeline
