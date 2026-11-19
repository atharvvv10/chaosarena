"""Isolation Forest anomaly detector and its persisted bundle.

The Isolation Forest score alone dilutes a single-service spike across 18
features. We add a bounded standardized-deviation term so a large deviation in
one feature is still visible while the forest remains the core model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from .features import FEATURE_NAMES

DEFAULT_MODEL = Path("ml/defender_model.joblib")
MODEL_VERSION = 3
DEVIATION_CAP = 0.5
DEVIATION_SCALE = 100.0
THRESHOLD_MARGIN = 0.12


@dataclass
class Detector:
    forest: IsolationForest
    threshold: float
    mean: np.ndarray
    std: np.ndarray
    feature_names: tuple[str, ...] = FEATURE_NAMES

    @classmethod
    def train(cls, rows: Sequence[Sequence[float]]) -> "Detector":
        matrix = np.asarray(rows, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] < 5 or matrix.shape[1] != len(FEATURE_NAMES):
            raise ValueError(
                f"need at least 5 rows of {len(FEATURE_NAMES)} features to train"
            )
        mean = np.mean(matrix, axis=0)
        std = np.std(matrix, axis=0)
        std = np.where(std < 1e-9, 1.0, std)

        forest = IsolationForest(
            n_estimators=200,
            contamination="auto",
            random_state=42,
            n_jobs=1,
        )
        forest.fit(matrix)
        detector = cls(forest=forest, threshold=0.0, mean=mean, std=std)
        scores = np.asarray([detector._raw_score(row) for row in matrix])
        spread = float(np.std(scores))
        # Use a high quantile plus a real margin: normal loadgen traffic moves
        # by a few percent between samples and must not be called an attack.
        detector.threshold = float(
            np.quantile(scores, 0.99) + max(THRESHOLD_MARGIN, 0.25 * spread)
        )
        return detector

    def _raw_score(self, vector: Sequence[float]) -> float:
        row = np.asarray(vector, dtype=float).reshape(1, -1)
        forest_score = float(-self.forest.score_samples(row)[0])
        z = np.abs((np.asarray(vector, dtype=float) - self.mean) / self.std)
        deviation = min(DEVIATION_CAP, float(np.max(z)) / DEVIATION_SCALE)
        return forest_score + deviation

    def score(self, vector: Sequence[float]) -> float:
        return self._raw_score(vector)

    def is_anomaly(self, vector: Sequence[float]) -> bool:
        return self.score(vector) > self.threshold

    def save(self, path: Path | str = DEFAULT_MODEL) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "version": MODEL_VERSION,
                "forest": self.forest,
                "threshold": self.threshold,
                "mean": self.mean,
                "std": self.std,
                "feature_names": tuple(self.feature_names),
            },
            target,
        )
        return target

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL) -> "Detector":
        payload = joblib.load(Path(path))
        if payload.get("version") != MODEL_VERSION:
            raise ValueError("unsupported model version; retrain the defender")
        return cls(
            forest=payload["forest"],
            threshold=float(payload["threshold"]),
            mean=np.asarray(payload["mean"], dtype=float),
            std=np.asarray(payload["std"], dtype=float),
            feature_names=tuple(payload["feature_names"]),
        )


def baseline_stats(rows: Sequence[Sequence[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Return per-feature mean and standard deviation for diagnosis."""
    matrix = np.asarray(rows, dtype=float)
    mean = np.mean(matrix, axis=0)
    std = np.std(matrix, axis=0)
    std = np.where(std < 1e-9, 1.0, std)
    return mean, std
