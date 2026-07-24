"""Tests for C.3 temperature-scaling calibration (Week 5).

Hermetic and deterministic: synthetic candidate-logit shortlists + 0/1 labels
only — no cross-encoder, DB, or embedding key. Covers the softmax-over-shortlist
confidence, temperature flatten/sharpen behaviour, the NLL fit recovering a known
T and reducing NLL, ECE on perfectly- and mis-calibrated data (hand-checked), and
every guard.
"""

import math
import unittest

import numpy as np
from scipy.special import softmax

from application.utils.librarian.calibration.temperature import (
    CALIBRATOR_NAME,
    CalibrationError,
    DegenerateLabelsError,
    TemperatureScaler,
    expected_calibration_error,
    fit_temperature,
    negative_log_likelihood,
)


class TemperatureScalerTest(unittest.TestCase):
    def test_confidence_is_softmax_top_mass(self) -> None:
        logits = [2.0, 1.0, 0.0]
        expected = float(softmax(np.array(logits)).max())
        self.assertAlmostEqual(TemperatureScaler(1.0).confidence(logits), expected, 9)

    def test_probabilities_sum_to_one_and_peak_at_top(self) -> None:
        p = TemperatureScaler(1.0).probabilities([3.0, 1.0, -2.0])
        self.assertAlmostEqual(float(p.sum()), 1.0, places=9)
        self.assertEqual(int(np.argmax(p)), 0)  # highest logit -> highest prob

    def test_high_temperature_flattens_toward_uniform(self) -> None:
        logits = [3.0, 1.0, 0.0]
        hot = TemperatureScaler(1000.0).confidence(logits)
        base = TemperatureScaler(1.0).confidence(logits)
        self.assertLess(hot, base)
        self.assertAlmostEqual(hot, 1.0 / 3.0, places=2)  # ~uniform over 3

    def test_low_temperature_sharpens_toward_one(self) -> None:
        logits = [3.0, 1.0, 0.0]
        cold = TemperatureScaler(0.1).confidence(logits)
        base = TemperatureScaler(1.0).confidence(logits)
        self.assertGreater(cold, base)
        self.assertGreater(cold, 0.99)

    def test_single_candidate_confidence_is_one(self) -> None:
        # softmax over one element is always 1.0, at any temperature.
        self.assertAlmostEqual(TemperatureScaler(3.0).confidence([0.42]), 1.0, 9)

    def test_empty_shortlist_rejected(self) -> None:
        with self.assertRaises(CalibrationError):
            TemperatureScaler(1.0).confidence([])

    def test_non_positive_or_nonfinite_temperature_rejected(self) -> None:
        for bad in (0.0, -1.0, float("inf"), float("nan")):
            with self.assertRaises(CalibrationError):
                TemperatureScaler(bad)


class NegativeLogLikelihoodTest(unittest.TestCase):
    def test_matches_hand_computed_single_pair(self) -> None:
        # one shortlist, top-1 correct: loss = -log(softmax([2,0]).max())
        conf = float(softmax(np.array([2.0, 0.0])).max())
        self.assertAlmostEqual(
            negative_log_likelihood([[2.0, 0.0]], [1.0], 1.0), -math.log(conf), 6
        )

    def test_length_mismatch_rejected(self) -> None:
        with self.assertRaises(CalibrationError):
            negative_log_likelihood([[1.0, 0.0], [2.0, 0.0]], [1.0], 1.0)

    def test_non_positive_temperature_rejected(self) -> None:
        with self.assertRaises(CalibrationError):
            negative_log_likelihood([[1.0, 0.0]], [1.0], 0.0)


class FitTemperatureTest(unittest.TestCase):
    def _synthetic(self, true_t: float, n: int = 4000, k: int = 5):
        """Shortlists whose top-1 correctness is drawn from softmax(logits/true_t).

        Data generated with true_t flattens the softmax, so the raw (T=1)
        confidence is over-confident and the fit should recover T ~ true_t.
        Seeded -> stable.
        """
        rng = np.random.default_rng(0)
        sets, labels = [], []
        for _ in range(n):
            z = rng.normal(0.0, 3.0, size=k)
            z[::-1].sort()  # descending so index 0 is the top-1 (argmax)
            p_correct = softmax(z / true_t).max()
            sets.append(z.tolist())
            labels.append(1.0 if rng.random() < p_correct else 0.0)
        return sets, labels

    def test_recovers_known_temperature(self) -> None:
        sets, labels = self._synthetic(true_t=2.0)
        scaler = fit_temperature(sets, labels)
        self.assertAlmostEqual(scaler.temperature, 2.0, delta=0.5)

    def test_fit_reduces_nll_versus_T1(self) -> None:
        sets, labels = self._synthetic(true_t=2.0)
        scaler = fit_temperature(sets, labels)
        self.assertLess(
            negative_log_likelihood(sets, labels, scaler.temperature),
            negative_log_likelihood(sets, labels, 1.0),
        )

    def test_single_class_labels_raise_degenerate(self) -> None:
        with self.assertRaises(DegenerateLabelsError):
            fit_temperature([[2.0, 0.0], [3.0, 1.0]], [1.0, 1.0])

    def test_non_binary_labels_rejected(self) -> None:
        with self.assertRaises(CalibrationError):
            fit_temperature([[2.0, 0.0], [3.0, 1.0]], [0.0, 2.0])


class ExpectedCalibrationErrorTest(unittest.TestCase):
    def test_perfectly_calibrated_is_near_zero(self) -> None:
        # bin [0.5,0.6): five correct, five wrong -> acc 0.5 == conf 0.5.
        self.assertAlmostEqual(
            expected_calibration_error([0.5] * 10, [1.0, 0.0] * 5), 0.0, places=6
        )

    def test_confidently_wrong_is_large(self) -> None:
        self.assertAlmostEqual(
            expected_calibration_error([0.9] * 10, [0.0] * 10), 0.9, places=6
        )

    def test_hand_checked_two_bin_value(self) -> None:
        # [0.2,0.3): conf .2 acc 0 gap .2 ; [0.8,0.9): conf .8 acc 1 gap .2
        # ECE = 0.5*0.2 + 0.5*0.2 = 0.20
        self.assertAlmostEqual(
            expected_calibration_error([0.2, 0.2, 0.8, 0.8], [0.0, 0.0, 1.0, 1.0]),
            0.20,
            places=6,
        )

    def test_length_mismatch_and_empty_rejected(self) -> None:
        with self.assertRaises(CalibrationError):
            expected_calibration_error([0.5, 0.6], [1.0])
        with self.assertRaises(CalibrationError):
            expected_calibration_error([], [])
        with self.assertRaises(CalibrationError):
            expected_calibration_error([0.5], [1.0], n_bins=0)


class EndToEndTest(unittest.TestCase):
    def test_flat_shortlists_are_low_confidence(self) -> None:
        # A near-tie shortlist (bad match) -> low top-1 confidence.
        self.assertLess(TemperatureScaler(1.0).confidence([0.1, 0.0, -0.1]), 0.45)

    def test_peaked_shortlist_is_high_confidence(self) -> None:
        # A clear winner -> high top-1 confidence.
        self.assertGreater(TemperatureScaler(1.0).confidence([6.0, -1.0, -3.0]), 0.9)


class MetadataTest(unittest.TestCase):
    def test_calibrator_name_is_versioned(self) -> None:
        self.assertEqual(CALIBRATOR_NAME, "temperature-scaling/0.2.0")


if __name__ == "__main__":
    unittest.main()
