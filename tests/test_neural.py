"""Tests for the LSTM autoencoder defender."""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from defender.collect import load_baseline
from defender.features import FEATURE_NAMES
from defender.neural import NeuralDetector


def test_neural_detector_trains_scores_and_round_trips(tmp_path):
    rows = load_baseline("ml/baseline.csv")[:25]
    detector = NeuralDetector(seed=1)
    metrics = detector.train(rows, epochs=5)
    assert metrics["samples"] == 25
    assert metrics["threshold"] > 0

    detector.reset()
    assert detector.score(rows[0]) == 0.0
    for row in rows[: detector.window]:
        value = detector.score(row)
    assert value > 0.0
    assert isinstance(detector.is_anomaly(rows[-1]), bool)

    path = detector.save(tmp_path / "defender.pt")
    loaded = NeuralDetector.load(path)
    assert loaded.threshold == pytest.approx(detector.threshold, abs=1e-6)
    assert loaded.n_features == len(FEATURE_NAMES)


def test_calibration_uses_held_out_windows():
    rows = load_baseline("ml/baseline.csv")
    detector = NeuralDetector(seed=2)
    detector.train(rows[:30], epochs=5)
    trained_threshold = detector.threshold
    threshold = detector.calibrate(rows[30:], quantile=0.99, margin=0.1)
    assert threshold > 0
    assert threshold != trained_threshold
