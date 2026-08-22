"""OIE PoC orchestrator — A → B → C for one ``pipeline_run_id``.

Designed for a local/demo environment. Does not modify Module A/B/C packages;
it only *calls* their public entry points when importable, and leaves explicit
``TODO:`` markers where a callable is missing or not yet on ``main``.

Entry-point status (as of 2026-07-24 PR survey):

* Module A (tip #987 ``week_5-clean``): **no** top-level entry. Components only
  (config, git client, change detector, file filter, diff retrieve/parse/
  normalize). No CLI flag, no ``run_harvester``, no ``harvest_input`` writer,
  no ChangeRecord/JSONL emitter.
* Module B (tip #989 ``module_b_w5``): **yes** —
  ``noise_filter.pipeline.run_noise_filter(session, pipeline_run_id, …)`` and
  ``cre.py --run_noise_filter --run_id …``. Not on ``main`` until #989 merges.
* Module C (``main`` + tip #991): **yes (partial)** —
  ``cre_main.run_librarian(cache, dry_run, source_jsonl)`` on ``main`` (C.0→C.2
  dry-run over a JSONL fixture). ``LibrarianPipeline.run(at=…)`` on #991
  (C.0→C.4 envelopes, still dry-run / no graph write). DB-backed
  ``knowledge_queue`` source is W8.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIBRARIAN_SOURCE = (
    "application/tests/librarian/fixtures/sample_knowledge_queue.jsonl"
)


@dataclass
class StageResult:
    """Outcome of one orchestrator stage (module A, B, or C)."""

    name: str
    status: str  # ok | skipped | todo | error
    detail: str
    summary: Optional[Dict[str, Any]] = None


@dataclass
class OrchestratorResult:
    """Full A→B→C run summary (JSON-serializable for PoC logging)."""

    run_id: str
    dry_run: bool
    stages: List[StageResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "stages": [asdict(s) for s in self.stages],
            "ok": all(s.status in ("ok", "skipped", "todo") for s in self.stages),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _stage_module_a(run_id: str, *, skip: bool) -> StageResult:
    """Module A (Harvester) — no callable entry point yet.

    TODO: Once Module A lands a top-level entry, call it here. Needed shape
    (either is fine for the orchestrator):

      # library
      run_harvester(pipeline_run_id=run_id, ...) -> RunSummary
        # must write ChangeRecord payloads into harvest_input (status=pending)

      # or CLI
      python cre.py --run_harvester --run_id <id> [--cache_file ...]

    Until then, Module B has nothing to read from ``harvest_input``. For a PoC
    that only demos B/C, pass ``skip_a=True`` and seed ``harvest_input`` (or a
    librarian JSONL fixture) out of band.
    """
    if skip:
        return StageResult(
            name="module_a_harvester",
            status="skipped",
            detail="skip_a=True; harvester not invoked",
        )
    return StageResult(
        name="module_a_harvester",
        status="todo",
        detail=(
            "TODO: Module A has no orchestrator entry point yet "
            "(stacked PRs #920→#987). Need run_harvester / --run_harvester that "
            f"writes harvest_input rows for pipeline_run_id={run_id!r}. "
            "Do not patch Module A from this orchestrator — land the entry in "
            "the harvester package, then wire the call here."
        ),
    )


def _stage_module_b(
    run_id: str,
    cache_file: str,
    *,
    skip: bool,
    dry_run: bool,
    run_noise_filter_fn: Optional[Callable[..., Any]] = None,
) -> StageResult:
    """Module B (Noise Filter) — call ``run_noise_filter`` when importable.

    TODO: Land / merge Module B PR #989 so ``application.utils.noise_filter.pipeline``
    and the ``harvest_input`` / ``knowledge_queue`` migration exist on ``main``.
    TODO: Until Module A writes ``harvest_input``, seed pending rows for
    ``pipeline_run_id`` manually (or keep skip_b and demo C from a JSONL fixture).
    """
    if skip:
        return StageResult(
            name="module_b_noise_filter",
            status="skipped",
            detail="skip_b=True; noise filter not invoked",
        )

    injected = run_noise_filter_fn is not None
    fn = run_noise_filter_fn
    if fn is None:
        try:
            from application.utils.noise_filter.pipeline import run_noise_filter

            fn = run_noise_filter
        except ImportError:
            return StageResult(
                name="module_b_noise_filter",
                status="todo",
                detail=(
                    "TODO: Module B orchestrator entry not on this branch. "
                    "Merge PR #989 (run_noise_filter + harvest_input/knowledge_queue), "
                    "then this stage will call "
                    "noise_filter.pipeline.run_noise_filter(session, "
                    f"pipeline_run_id={run_id!r}, dry_run={dry_run}). "
                    "CLI equivalent after #989: "
                    f"python cre.py --run_noise_filter --run_id {run_id} "
                    "[--noise_filter_dry_run]."
                ),
            )

    try:
        session: Any = None
        if not injected:
            from application import sqla  # type: ignore[attr-defined]
            from application.cmd.cre_main import db_connect

            db_connect(cache_file)
            session = sqla.session
        summary = fn(session, run_id, dry_run=dry_run)
        summary_dict: Dict[str, Any]
        if hasattr(summary, "to_json"):
            summary_dict = json.loads(summary.to_json())
        elif hasattr(summary, "__dict__"):
            summary_dict = dict(summary.__dict__)
        else:
            summary_dict = {"raw": str(summary)}
        return StageResult(
            name="module_b_noise_filter",
            status="ok",
            detail=f"run_noise_filter completed for run_id={run_id!r}",
            summary=summary_dict,
        )
    except Exception as exc:  # noqa: BLE001 — PoC boundary; report and continue
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
    source_jsonl: Optional[str],
    run_librarian_fn: Optional[Callable[..., Any]] = None,
) -> StageResult:
    """Module C (Librarian) — prefer CLI dry-run entry on ``main``.

    Available now on ``main``:
      cre_main.run_librarian(cache_file, dry_run=True, source_jsonl=…)
      # CLI: python cre.py --librarian_dry_run [--librarian_source PATH]

    TODO: After Module C #991 merges, prefer
      LibrarianPipeline(source, retriever, reranker, scaler,
                       threshold=…, pipeline_run_id=run_id).run(at=…)
      and emit LinkProposal | ReviewItem envelopes. Keep dry-run until W8
      graph / queue write-back exists.
    TODO: Replace FixtureKnowledgeSource / JSONL with a DB-backed
      KnowledgeSource that polls ``knowledge_queue`` where
      ``pipeline_run_id == run_id`` and ``consumed_at IS NULL`` (Module C W8).
    TODO: cre_main.run_librarian on tip #991 still uses the W3 C.0→C.2 path;
      wire it to LibrarianPipeline when that glue is ready — do not fork
      Module C inside this orchestrator.
    """
    if skip:
        return StageResult(
            name="module_c_librarian",
            status="skipped",
            detail="skip_c=True; librarian not invoked",
        )

    jsonl = source_jsonl or DEFAULT_LIBRARIAN_SOURCE
    fn = run_librarian_fn
    if fn is None:
        try:
            from application.utils.librarian.pipeline import LibrarianPipeline

            # TODO: Build a real LibrarianPipeline (retriever/reranker/scaler +
            # DB KnowledgeSource) once #991 is on main and a component factory
            # exists. Until then fall through to run_librarian below.
            _ = LibrarianPipeline  # import proves the symbol exists
            logger.info(
                "LibrarianPipeline is importable (Module C #991+); "
                "orchestrator still uses run_librarian until a production "
                "component factory is available (TODO)."
            )
        except ImportError:
            pass

        from application.cmd.cre_main import run_librarian

        fn = run_librarian

    try:
        # run_librarian ignores pipeline_run_id today (fixture stream); recorded
        # for correlation in the orchestrator summary.
        fn(cache_file, dry_run=dry_run, source_jsonl=jsonl)
        return StageResult(
            name="module_c_librarian",
            status="ok",
            detail=(
                f"run_librarian completed (dry_run={dry_run}, source={jsonl}, "
                f"pipeline_run_id={run_id!r} for correlation only)"
            ),
            summary={"source_jsonl": jsonl, "pipeline_run_id": run_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Module C stage failed")
        return StageResult(
            name="module_c_librarian",
            status="error",
            detail=f"run_librarian failed: {exc}",
        )


def run_oie_demo_pipeline(
    *,
    cache_file: str,
    pipeline_run_id: Optional[str] = None,
    skip_a: bool = True,
    skip_b: bool = False,
    skip_c: bool = False,
    librarian_source_jsonl: Optional[str] = None,
    dry_run: bool = True,
    run_noise_filter_fn: Optional[Callable[..., Any]] = None,
    run_librarian_fn: Optional[Callable[..., Any]] = None,
) -> OrchestratorResult:
    """Run the PoC A→B→C sequence for one ``pipeline_run_id``.

    Defaults skip Module A (no entry point) and run B/C in dry-run-friendly
    mode. Inject ``run_*_fn`` in tests to avoid hitting the real DB/LLM.
    """
    run_id = (pipeline_run_id or "").strip() or str(uuid.uuid4())
    result = OrchestratorResult(run_id=run_id, dry_run=dry_run)

    result.stages.append(_stage_module_a(run_id, skip=skip_a))
    result.stages.append(
        _stage_module_b(
            run_id,
            cache_file,
            skip=skip_b,
            dry_run=dry_run,
            run_noise_filter_fn=run_noise_filter_fn,
        )
    )
    result.stages.append(
        _stage_module_c(
            run_id,
            cache_file,
            skip=skip_c,
            dry_run=dry_run,
            source_jsonl=librarian_source_jsonl,
            run_librarian_fn=run_librarian_fn,
        )
    )
    return result
