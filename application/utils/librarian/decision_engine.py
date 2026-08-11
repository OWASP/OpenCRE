"""Module C.4 — the decision engine (Week 6). The gatekeeper.

C.3 hands up one calibrated confidence: "how likely is the top reranked candidate
the correct CRE?" C.4 turns that honest number into an action — **auto-link** the
chunk into the OpenCRE graph, or **route it to a human** for review. That choice is
the accuracy gate of the whole pipeline, so the rule is deliberately small and total:

    - no candidate at all            -> review (NO_CANDIDATES)
    - a blocking safety flag         -> review (ADVERSARIAL_FLAG / UPDATE_AMBIGUOUS)
    - confidence below the threshold -> review (BELOW_THRESHOLD)
    - otherwise                      -> auto-link the top-1 candidate

Like C.1/C.2/C.3 this is a thin, model-free seam: a pure function of
``(confidence, candidates, flags, threshold)`` -> ``DecisionResult``. It does **not**
import the C.3 ``TemperatureScaler`` — it consumes the confidence that scaler already
produced — so it is hermetically testable and agnostic to how the number was made.
Turning a ``DecisionResult`` into the RFC ``LinkProposal`` / ``ReviewItem`` envelope
(which needs the full chunk context) is the emitter's job, wired in the pipeline.

Reason-code precedence when several conditions hold at once:
``NO_CANDIDATES > ADVERSARIAL_FLAG > UPDATE_AMBIGUOUS > BELOW_THRESHOLD``. A safety
flag is surfaced to the reviewer ahead of a mere low-confidence note, because it is
the more important thing for a human to see; you cannot link nothing, so the empty
shortlist dominates everything.
"""

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from application.utils.librarian.schemas import Decision, ReasonCode

# Identify the engine in the RFC audit trail (mirrors RETRIEVER_NAME /
# RERANKER_NAME / CALIBRATOR_NAME).
ENGINE_NAME = "decision-engine/0.1.0"


class DecisionError(ValueError):
    """Raised on decision-engine misuse (bad threshold or confidence)."""


@dataclass(frozen=True)
class DecisionResult:
    """The verdict for one chunk. Frozen so it is a stable, loggable value.

    ``cre_ids`` is the top-1 candidate: the CRE that gets linked when
    ``decision == linked``, or the reviewer's best-guess suggestion when
    ``decision == review`` (empty only when there were no candidates at all).
    ``reason_code`` is set iff ``decision == review``.
    """

    decision: Decision
    confidence: float
    cre_ids: Tuple[str, ...]
    reason_code: Optional[ReasonCode] = None


def _validate(confidence: float, threshold: float) -> None:
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise DecisionError(f"threshold must be finite in [0, 1], got {threshold}")
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise DecisionError(f"confidence must be finite in [0, 1], got {confidence}")


def decide(
    confidence: float,
    candidate_cre_ids: Sequence[str],
    *,
    threshold: float,
    adversarial: bool = False,
    update_ambiguous: bool = False,
) -> DecisionResult:
    """Apply the auto-link rule to one chunk's calibrated confidence.

    ``candidate_cre_ids`` is the reranked shortlist, best first (may be empty).
    ``threshold`` is the auto-link bar τ (``LibrarianConfig.link_threshold``); a
    chunk links only when ``confidence >= threshold``. ``adversarial`` /
    ``update_ambiguous`` are blocking flags from the SafetyGuard (both default
    False until it is wired) — either one forces review regardless of confidence.
    """
    _validate(confidence, threshold)

    top = tuple(candidate_cre_ids[:1])

    if not candidate_cre_ids:
        return DecisionResult(Decision.review, confidence, (), ReasonCode.no_candidates)
    if adversarial:
        return DecisionResult(
            Decision.review, confidence, top, ReasonCode.adversarial_flag
        )
    if update_ambiguous:
        return DecisionResult(
            Decision.review, confidence, top, ReasonCode.update_ambiguous
        )
    if confidence < threshold:
        return DecisionResult(
            Decision.review, confidence, top, ReasonCode.below_threshold
        )
    return DecisionResult(Decision.linked, confidence, top, None)
