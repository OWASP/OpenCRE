"""Phase 3/7: LangGraph-compatible decide node that calls OpenCRE decide().

Frameworks orchestrate; they do **not** own auto-link policy.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Sequence

from application.utils.librarian.decision_engine import DecisionResult, decide


def opencre_decide_node(state: Mapping[str, Any]) -> Dict[str, Any]:
    """LangGraph node: read confidence/candidates/τ from state → OpenCRE decide()."""
    confidence = float(state.get("confidence", 0.0))
    threshold = float(state.get("threshold", state.get("tau", 0.8)))
    candidates: Sequence[str] = list(state.get("candidate_cre_ids") or [])
    result: DecisionResult = decide(
        confidence,
        candidates,
        threshold=threshold,
        adversarial=bool(state.get("adversarial", False)),
        update_ambiguous=bool(state.get("update_ambiguous", False)),
    )
    out: Dict[str, Any] = {
        "decision": (
            result.decision.value
            if hasattr(result.decision, "value")
            else str(result.decision)
        ),
        "confidence": result.confidence,
        "cre_ids": list(result.cre_ids),
        "reason_code": (
            result.reason_code.value
            if result.reason_code is not None and hasattr(result.reason_code, "value")
            else (str(result.reason_code) if result.reason_code else None)
        ),
        "policy": "opencre.decide",
    }
    return out


def attach_decide_node(graph: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Register the decide node on a simple graph dict (LangGraph-agnostic stub)."""
    graph["nodes"] = dict(graph.get("nodes") or {})
    graph["nodes"]["opencre_decide"] = opencre_decide_node
    return graph
