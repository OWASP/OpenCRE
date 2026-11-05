"""OIE A→B→C orchestrator package."""

from cre_logging import get_logger

logger = get_logger(__name__)

from .pipeline import (
    OrchestratorResult,
    StageResult,
    run_oie_demo_pipeline,
    run_oie_pipeline,
)

__all__ = [
    "OrchestratorResult",
    "StageResult",
    "run_oie_demo_pipeline",
    "run_oie_pipeline",
]
