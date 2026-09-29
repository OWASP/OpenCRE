"""LangGraph + LlamaIndex-backed OIE orchestrator (A → B → C).

LangGraph owns stage sequencing. LlamaIndex/Docling live under Module A's
``strategy: docling`` chunk path. Existing module entrypoints and DB queue
contracts are unchanged — this module only rewires *how* stages are invoked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypedDict

from application.utils.oie_orchestrator.pipeline import (
    OrchestratorResult,
    StageResult,
    _connect,
    _stage_status_from_summary,
    _summary_dict,
)

logger = logging.getLogger(__name__)


class OieState(TypedDict, total=False):
    run_id: str
    cache_file: str
    dry_run: bool
    sync_repos: bool
    skip_a: bool
    skip_b: bool
    skip_c: bool
    stop_on_error: bool
    stage_a: Dict[str, Any]
    stage_b: Dict[str, Any]
    stage_c: Dict[str, Any]
    halt: bool


def _stage_to_dict(stage: StageResult) -> Dict[str, Any]:
    return {
        "name": stage.name,
        "status": stage.status,
        "detail": stage.detail,
        "summary": stage.summary,
    }


def _run_a(
    state: OieState, run_harvester_fn: Optional[Callable[..., Any]]
) -> Dict[str, Any]:
    if state.get("halt"):
        return {}
    if state.get("skip_a"):
        stage = StageResult(
            name="module_a_harvester",
            status="skipped",
            detail="skip_a=True; harvester not invoked",
        )
        return {"stage_a": _stage_to_dict(stage)}

    fn = run_harvester_fn
    if fn is None:
        from application.utils.harvester.pipeline import run_harvester

        fn = run_harvester
    try:
        session = _connect(state["cache_file"])
        summary = fn(
            session,
            state["run_id"],
            dry_run=bool(state.get("dry_run")),
            sync_repos=bool(state.get("sync_repos", True)),
        )
        stage = StageResult(
            name="module_a_harvester",
            status=_stage_status_from_summary(summary),
            detail=f"run_harvester completed for run_id={state['run_id']!r}",
            summary=_summary_dict(summary),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module A stage failed")
        stage = StageResult(
            name="module_a_harvester",
            status="error",
            detail=f"run_harvester failed: {exc}",
        )
    halt = bool(state.get("stop_on_error", True)) and stage.status == "error"
    return {"stage_a": _stage_to_dict(stage), "halt": halt}


def _run_b(
    state: OieState, run_noise_filter_fn: Optional[Callable[..., Any]]
) -> Dict[str, Any]:
    if state.get("halt"):
        return {
            "stage_b": _stage_to_dict(
                StageResult(
                    name="module_b_noise_filter",
                    status="skipped",
                    detail="halted after earlier stage error",
                )
            )
        }
    if state.get("skip_b"):
        return {
            "stage_b": _stage_to_dict(
                StageResult(
                    name="module_b_noise_filter",
                    status="skipped",
                    detail="skip_b=True; noise filter not invoked",
                )
            )
        }

    fn = run_noise_filter_fn
    if fn is None:
        from application.utils.noise_filter.pipeline import run_noise_filter

        fn = run_noise_filter
    try:
        session = _connect(state["cache_file"])
        summary = fn(session, state["run_id"], dry_run=bool(state.get("dry_run")))
        stage = StageResult(
            name="module_b_noise_filter",
            status=_stage_status_from_summary(summary),
            detail=f"run_noise_filter completed for run_id={state['run_id']!r}",
            summary=_summary_dict(summary),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module B stage failed")
        stage = StageResult(
            name="module_b_noise_filter",
            status="error",
            detail=f"run_noise_filter failed: {exc}",
        )
    halt = bool(state.get("stop_on_error", True)) and stage.status == "error"
    return {"stage_b": _stage_to_dict(stage), "halt": halt}


def _run_c(
    state: OieState, run_librarian_queue_fn: Optional[Callable[..., Any]]
) -> Dict[str, Any]:
    if state.get("halt"):
        return {
            "stage_c": _stage_to_dict(
                StageResult(
                    name="module_c_librarian",
                    status="skipped",
                    detail="halted after earlier stage error",
                )
            )
        }
    if state.get("skip_c"):
        return {
            "stage_c": _stage_to_dict(
                StageResult(
                    name="module_c_librarian",
                    status="skipped",
                    detail="skip_c=True; librarian not invoked",
                )
            )
        }

    try:
        if run_librarian_queue_fn is not None:
            summary = run_librarian_queue_fn(
                state["run_id"], dry_run=bool(state.get("dry_run"))
            )
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
            database = db_connect(path=state["cache_file"])
            components = build_components(database, config=cfg)
            sink = (
                NullEnvelopeSink()
                if state.get("dry_run")
                else DbEnvelopeSink(database.session, state["run_id"])
            )
            summary = run_librarian_queue(
                database.session,
                state["run_id"],
                components,
                cfg,
                at=datetime.now(timezone.utc),
                sink=sink,
                dry_run=bool(state.get("dry_run")),
            )
        stage = StageResult(
            name="module_c_librarian",
            status=_stage_status_from_summary(summary),
            detail=f"run_librarian_queue completed for run_id={state['run_id']!r}",
            summary=(
                _summary_dict(summary) if not isinstance(summary, dict) else summary
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module C stage failed")
        stage = StageResult(
            name="module_c_librarian",
            status="error",
            detail=f"run_librarian_queue failed: {exc}",
        )
    return {"stage_c": _stage_to_dict(stage)}


def run_oie_pipeline_langgraph(
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
    """Compile a LangGraph ``A → B → C`` and invoke it once."""
    from langgraph.graph import END, START, StateGraph

    run_id = (pipeline_run_id or "").strip() or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )

    graph = StateGraph(OieState)
    graph.add_node("module_a", lambda s: _run_a(s, run_harvester_fn))
    graph.add_node("module_b", lambda s: _run_b(s, run_noise_filter_fn))
    graph.add_node("module_c", lambda s: _run_c(s, run_librarian_queue_fn))
    graph.add_edge(START, "module_a")
    graph.add_edge("module_a", "module_b")
    graph.add_edge("module_b", "module_c")
    graph.add_edge("module_c", END)
    app = graph.compile()

    final = app.invoke(
        {
            "run_id": run_id,
            "cache_file": cache_file,
            "dry_run": dry_run,
            "sync_repos": sync_repos,
            "skip_a": skip_a,
            "skip_b": skip_b,
            "skip_c": skip_c,
            "stop_on_error": stop_on_error,
            "halt": False,
        }
    )

    result = OrchestratorResult(run_id=run_id, dry_run=dry_run)
    for key in ("stage_a", "stage_b", "stage_c"):
        raw = final.get(key)
        if not raw:
            continue
        result.stages.append(
            StageResult(
                name=raw["name"],
                status=raw["status"],
                detail=raw["detail"],
                summary=raw.get("summary"),
            )
        )
    return result
