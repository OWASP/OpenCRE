"""OIE orchestrator — A → B → C for one ``pipeline_run_id``.

Production sequencing: run each stage, wait for process/library return,
then start the next. Modules communicate only through DB tables:

  A writes ``harvest_input`` → B writes ``knowledge_queue`` → C writes
  ``decision_queue`` / stamps ``consumed_at``.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


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
    engine: str = "sequential"  # langgraph | sequential
    sync_repos: bool = True
    skip_a: bool = False
    skip_b: bool = False
    skip_c: bool = False
    stop_on_error: bool = True
    max_repos: Optional[int] = None
    repos_yaml: Optional[str] = None
    graph_path: List[str] = field(
        default_factory=lambda: [
            "START",
            "module_a_harvester",
            "module_b_noise_filter",
            "module_c_librarian",
            "END",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        visited = [
            {
                "name": s.name,
                "status": s.status,
                "invoked": s.status not in ("skipped",),
                "detail": s.detail,
            }
            for s in self.stages
        ]
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "engine": self.engine,
            "flags": {
                "dry_run": self.dry_run,
                "sync_repos": self.sync_repos,
                "skip_a": self.skip_a,
                "skip_b": self.skip_b,
                "skip_c": self.skip_c,
                "stop_on_error": self.stop_on_error,
                "max_repos": self.max_repos,
                "repos_yaml": self.repos_yaml,
            },
            "graph_path": list(self.graph_path),
            "visited": visited,
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


def _skip_stage_detail(flag: str, module: str) -> str:
    """Explain why a stage was not invoked (flags are explicit at call time)."""
    return (
        f"{flag}=True; {module} not invoked. "
        "Caller passed this skip flag (admin ingest defaults skip_b/skip_c "
        "unless the client sets them false)."
    )


def _harvester_detail(run_id: str, summary: Any) -> str:
    data = _summary_dict(summary) or {}
    base = (
        f"run_harvester completed for run_id={run_id!r} "
        f"status={data.get('status')!r} errors={data.get('errors')} "
        f"chunks={data.get('chunks_written')} files={data.get('files_retained')} "
        f"repos={data.get('repository_ids') or data.get('repositories')}"
    )
    reasons: List[str] = []
    chunks = data.get("chunks_written") or 0
    repos = data.get("repositories") or 0
    if repos and not chunks:
        files_seen = data.get("files_seen") or 0
        retained = data.get("files_retained") or 0
        emitted = data.get("documents_emitted") or 0
        if files_seen == 0:
            reasons.append(
                "no file diffs since harvester_checkpoint (repos already at HEAD)"
            )
        elif retained == 0:
            reasons.append("files seen but none matched include/exclude globs")
        elif emitted == 0:
            reasons.append("documents unchanged vs artifact registry (deduped)")
        else:
            reasons.append("chunking produced no writable records")
    if data.get("skipped_not_due"):
        reasons.append(f"skipped_not_due={data.get('skipped_not_due')}")
    if data.get("deferred"):
        reasons.append(f"deferred={data.get('deferred')}")
    if not reasons:
        return base
    return base + " | " + "; ".join(reasons)


def _stage_module_a(
    run_id: str,
    cache_file: str,
    *,
    skip: bool,
    dry_run: bool,
    sync_repos: bool,
    run_harvester_fn: Optional[Callable[..., Any]] = None,
    repos_yaml: Optional[str] = None,
    max_repos: Optional[int] = None,
) -> StageResult:
    if skip:
        return StageResult(
            name="module_a_harvester",
            status="skipped",
            detail=_skip_stage_detail("skip_a", "harvester"),
        )

    fn = run_harvester_fn
    if fn is None:
        from application.utils.harvester.pipeline import run_harvester

        fn = run_harvester

    try:
        session = _connect(cache_file)
        kwargs: Dict[str, Any] = {
            "dry_run": dry_run,
            "sync_repos": sync_repos,
            "repos_yaml": repos_yaml,
        }
        if max_repos is not None:
            kwargs["max_repos"] = max_repos
        summary = fn(session, run_id, **kwargs)
        return StageResult(
            name="module_a_harvester",
            status=_stage_status_from_summary(summary),
            detail=_harvester_detail(run_id, summary),
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
            detail=_skip_stage_detail("skip_b", "noise filter"),
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
            detail=_skip_stage_detail("skip_c", "librarian"),
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
    use_langgraph: bool = True,
    repos_yaml: Optional[str] = None,
    max_repos: Optional[int] = None,
) -> OrchestratorResult:
    """
    Run A→B→C for one ``pipeline_run_id``.

    Default path uses LangGraph (``langgraph_pipeline``). Set
    ``use_langgraph=False`` for the legacy sequential stages (tests/smoke).
    """
    if use_langgraph:
        try:
            from application.utils.oie_orchestrator.langgraph_pipeline import (
                run_oie_pipeline_langgraph,
            )

            return run_oie_pipeline_langgraph(
                cache_file=cache_file,
                pipeline_run_id=pipeline_run_id,
                skip_a=skip_a,
                skip_b=skip_b,
                skip_c=skip_c,
                dry_run=dry_run,
                sync_repos=sync_repos,
                stop_on_error=stop_on_error,
                run_harvester_fn=run_harvester_fn,
                run_noise_filter_fn=run_noise_filter_fn,
                run_librarian_queue_fn=run_librarian_queue_fn,
                repos_yaml=repos_yaml,
                max_repos=max_repos,
            )
        except ImportError:
            logger.warning(
                "langgraph not installed; falling back to sequential orchestrator"
            )

    run_id = (pipeline_run_id or "").strip() or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    result = OrchestratorResult(
        run_id=run_id,
        dry_run=dry_run,
        engine="sequential",
        sync_repos=sync_repos,
        skip_a=skip_a,
        skip_b=skip_b,
        skip_c=skip_c,
        stop_on_error=stop_on_error,
        max_repos=max_repos,
        repos_yaml=repos_yaml,
    )

    a = _stage_module_a(
        run_id,
        cache_file,
        skip=skip_a,
        dry_run=dry_run,
        sync_repos=sync_repos,
        run_harvester_fn=run_harvester_fn,
        repos_yaml=repos_yaml,
        max_repos=max_repos,
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
