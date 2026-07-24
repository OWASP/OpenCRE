"""Module C.3 — temperature-scaling calibration (Week 5). The truth-teller.

C.2 hands up a reranked shortlist of candidate CREs, each with a raw cross-encoder
logit (unbounded, higher = better match). We need one honest number: "how likely
is the top candidate the correct CRE?" — so Week 6 can threshold auto-link vs.
human review.

The naive attempt — ``sigmoid(top1_logit / T)`` on the single absolute logit —
does not work, and the golden set proves why: a cross-encoder's absolute logit has
no fixed zero point (its 50/50 boundary is not at z=0), and dividing by a single
temperature can only *squash* toward 0.5, never *shift* the boundary. So no T
makes it honest.

The fix is **temperature scaling in the Guo et al. sense**: calibrate the *softmax
over the whole shortlist*, not one absolute logit. The candidates' *relative*
logits are what a cross-encoder's scores actually mean, so

    p = softmax(logits / T)          confidence = p for the top-1 candidate

is a genuine probability distribution over "which candidate is right", and its
top-1 mass answers exactly the question Week 6 asks. It is still **one knob T**:
T = 1 leaves the distribution unchanged, T > 1 flattens it (less confident), T < 1
sharpens it. T is fit once by minimising negative-log-likelihood of "is the top-1
correct?" on the golden set; honesty is measured by Expected Calibration Error,
and the Week 5 gate is ECE < 0.10.

Like C.1/C.2 this is a thin, model-free seam (numpy + scipy only) so every branch
is hermetically testable. The fitted ``TemperatureScaler`` is a frozen, shareable
artifact the W6 decision engine loads to turn a reranked shortlist into the
confidence it thresholds on.
"""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import softmax

# Identify the calibrator in the RFC audit trail (mirrors RETRIEVER_NAME /
# RERANKER_NAME). 0.2.0 = softmax-over-shortlist (the single-logit sigmoid of
# 0.1.0 could not be calibrated by temperature alone — see module docstring).
CALIBRATOR_NAME = "temperature-scaling/0.2.0"

# Clip probabilities off {0, 1} so the log in NLL stays finite.
_EPS = 1e-7


class CalibrationError(ValueError):
    """Base class for calibration construction/usage failures."""


class DegenerateLabelsError(CalibrationError):
    """Labels are single-class — temperature is unidentifiable from NLL.

    With only correct (or only incorrect) top-1s, NLL is monotonic in ``T`` and
    the optimum runs to a bound: the fit is meaningless. The calibration set must
    contain both outcomes (in the harness: the ``positive`` slice supplies
    correct top-1s, ``hard_negative`` supplies incorrect ones).
    """


def _softmax_top(logits: Sequence[float], temperature: float) -> float:
    """Top-1 probability mass of ``softmax(logits / T)`` over one shortlist."""
    z = np.asarray(list(logits), dtype=float)
    if z.size == 0:
        raise CalibrationError("cannot calibrate an empty candidate shortlist")
    return float(softmax(z / temperature).max())


def _validate_temperature(temperature: float) -> None:
    if not np.isfinite(temperature) or temperature <= 0:
        raise CalibrationError(f"temperature must be finite and > 0, got {temperature}")


def _paired(logit_sets: Sequence[Sequence[float]], labels: Sequence[float]):
    """Validate matched (shortlist, label) inputs: non-empty and equal length."""
    sets = list(logit_sets)
    y = np.asarray(list(labels), dtype=float)
    if y.ndim != 1:
        raise CalibrationError(f"labels must be 1-D, got shape {y.shape}")
    if len(sets) != y.shape[0]:
        raise CalibrationError(
            f"{len(sets)} logit-sets and {y.shape[0]} labels must be the same length"
        )
    if not sets:
        raise CalibrationError("need at least one (shortlist, label) pair")
    return sets, y


@dataclass(frozen=True)
class TemperatureScaler:
    """Maps a reranked shortlist to a calibrated top-1 confidence.

    ``temperature`` is the single learned scalar; build one with
    ``fit_temperature``. Frozen so a fitted scaler is a stable, shareable value
    (like the retriever/reranker being constructed once and reused).
    """

    temperature: float

    def __post_init__(self) -> None:
        _validate_temperature(self.temperature)

    def probabilities(self, logits: Sequence[float]) -> np.ndarray:
        """The full ``softmax(logits / T)`` distribution over one shortlist."""
        z = np.asarray(list(logits), dtype=float)
        if z.size == 0:
            raise CalibrationError("cannot calibrate an empty candidate shortlist")
        return softmax(z / self.temperature)

    def confidence(self, logits: Sequence[float]) -> float:
        """P(the top candidate is correct) — the top-1 mass of the softmax.

        This is the number the W6 decision engine thresholds on.
        """
        return _softmax_top(logits, self.temperature)


def negative_log_likelihood(
    logit_sets: Sequence[Sequence[float]],
    labels: Sequence[float],
    temperature: float,
) -> float:
    """Binary cross-entropy of the top-1 confidence against 0/1 correctness.

    For each shortlist the confidence is ``softmax(logits / T)``'s top-1 mass;
    the label is 1 iff that top-1 candidate is the correct CRE. This is the
    objective ``fit_temperature`` minimises over ``T``; exposed so the fit is
    testable and a caller can compare NLL at ``T=1`` vs the fitted T.
    """
    _validate_temperature(temperature)
    sets, y = _paired(logit_sets, labels)
    p = np.clip(
        np.array([_softmax_top(s, temperature) for s in sets]), _EPS, 1.0 - _EPS
    )
    return float(-np.sum(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def fit_temperature(
    logit_sets: Sequence[Sequence[float]],
    labels: Sequence[float],
    *,
    bounds: tuple = (1e-2, 1e2),
) -> TemperatureScaler:
    """Fit ``T`` by minimising NLL over (shortlist, is-top1-correct) pairs.

    ``labels`` must be 0/1 and contain both outcomes (else
    ``DegenerateLabelsError``). One free parameter over a bounded interval, so
    the 1-D ``minimize_scalar`` fit is fast and barely over-fits — the golden set
    is the calibration set by design.
    """
    sets, y = _paired(logit_sets, labels)
    values = set(np.unique(y).tolist())
    if not values <= {0.0, 1.0}:
        raise CalibrationError(f"labels must be 0/1, got values {sorted(values)}")
    if len(values) < 2:
        raise DegenerateLabelsError(
            "labels are single-class; temperature is unidentifiable — the "
            "calibration set needs both correct and incorrect top-1s"
        )

    result = minimize_scalar(
        lambda t: negative_log_likelihood(sets, y, t),
        bounds=bounds,
        method="bounded",
    )
    if not result.success:
        raise CalibrationError(f"temperature fit did not converge: {result.message}")
    return TemperatureScaler(temperature=float(result.x))


def expected_calibration_error(
    confidences: Sequence[float], labels: Sequence[float], *, n_bins: int = 10
) -> float:
    """ECE — sample-weighted mean ``|accuracy - confidence|`` across equal bins.

    Partition [0, 1] into ``n_bins`` equal-width bins. Per bin, ``confidence`` is
    the mean predicted top-1 probability and ``accuracy`` is the fraction whose
    top-1 was actually correct; ECE weights each bin's gap by its share of the
    sample. 0 = perfectly honest; the Week 5 gate is < 0.10.
    """
    if n_bins < 1:
        raise CalibrationError(f"n_bins must be >= 1, got {n_bins}")
    p = np.asarray(list(confidences), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    if p.shape != y.shape:
        raise CalibrationError(
            f"confidences {p.shape} and labels {y.shape} must be the same length"
        )
    if p.size == 0:
        raise CalibrationError("need at least one (confidence, label) pair")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)

    n = p.size
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        confidence = float(p[mask].mean())
        accuracy = float(y[mask].mean())
        ece += (count / n) * abs(accuracy - confidence)
    return ece
