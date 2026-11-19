"""Turn an anomaly into a human-readable, evidence-based diagnosis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .features import FEATURE_NAMES, METRICS, SERVICES


@dataclass
class Diagnosis:
    category: str
    service: str
    confidence: float
    evidence: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "service": self.service,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
        }


def diagnose(
    vector: Sequence[float],
    mean: np.ndarray,
    std: np.ndarray,
    top_n: int = 3,
) -> Diagnosis:
    """Rank deviating features and classify the most likely fault family."""
    values = np.asarray(vector, dtype=float)
    z_scores = (values - mean) / std
    order = np.argsort(-np.abs(z_scores))[:top_n]
    evidence = [
        f"{FEATURE_NAMES[i]} z={z_scores[i]:+.1f}" for i in order
    ]

    candidates: list[tuple[str, int, float, str, str]] = []
    for index, name in enumerate(FEATURE_NAMES):
        service, metric = next(
            (service, metric)
            for service in SERVICES
            for metric in METRICS
            if name == f"{service}_{metric}"
        )
        candidates.append((name, index, float(z_scores[index]), service, metric))

    # Latency and errors are causes; a request-rate drop is usually their
    # symptom (a slow service makes the whole chain slower), so check them first.
    latency = [c for c in candidates if c[4] == "p95_latency" and c[2] > 3]
    errors = [c for c in candidates if c[4] == "error_rate" and c[2] > 3]
    drops = [c for c in candidates if c[4] == "request_rate" and c[2] < -3]

    if latency:
        chosen = max(latency, key=lambda c: c[2])
        category = "latency_spike"
    elif errors:
        chosen = max(errors, key=lambda c: c[2])
        category = "error_spike"
    elif drops:
        chosen = min(drops, key=lambda c: c[2])
        category = "traffic_drop"
    else:
        chosen = next(c for c in candidates if c[1] == order[0])
        category = "unknown"

    _, strongest, strongest_z, service, _ = chosen
    strongest = int(strongest)
    confidence = min(0.99, abs(strongest_z) / 8.0)
    return Diagnosis(
        category=category,
        service=service,
        confidence=confidence,
        evidence=evidence,
    )
