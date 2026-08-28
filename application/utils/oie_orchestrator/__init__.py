"""PoC orchestrator for the OpenCRE Information Extraction (OIE) pipeline.

Wires Module A (Harvester) → Module B (Noise Filter) → Module C (Librarian)
for a single ``pipeline_run_id`` in a demo/local environment.

Module entry points are invoked only when present on the branch; missing
hooks are recorded as ``todo`` / ``skipped`` stages rather than patched
inside Modules A/B/C. See ``pipeline.py`` for the per-module TODO list.
"""

from application.utils.oie_orchestrator.pipeline import (
    OrchestratorResult,
    StageResult,
    run_oie_demo_pipeline,
)

__all__ = [
    "OrchestratorResult",
    "StageResult",
    "run_oie_demo_pipeline",
]
