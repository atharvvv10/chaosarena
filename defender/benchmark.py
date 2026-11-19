"""Reproducible detector comparison: rule-based vs Isolation Forest vs Defender.

This is an OFFLINE benchmark, not a live cluster battle. It uses the committed
40-sample normal baseline (`ml/baseline.csv`) plus seeded fault signatures
injected into copies of those rows, so it is fully reproducible with a fixed
seed. It exists to answer "why an Isolation Forest instead of a simple rule?"

Three detectors are compared on the same labelled rows:

1. rule_based_3sigma - flag when any single standardised feature exceeds 3 sigma.
2. isolation_forest_only - flag on the forest score alone (no deviation term).
3. defender - the shipped model: forest score + capped deviation term.

All three use statistics learned from the same normal baseline, so the
comparison is like-for-like.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np

from .collect import DEFAULT_BASELINE, load_baseline
from .features import FEATURE_NAMES
from .model import DEFAULT_MODEL, Detector, baseline_stats

RULE_Z = 3.0
DEFAULT_OUTPUT = Path("ml/defender_benchmark.json")
ATTACK_PATTERNS = ("latency_spike", "error_spike", "traffic_drop", "subtle_latency")


def seeded_attacks(rows: Sequence[Sequence[float]], seed: int = 7) -> list[list[float]]:
    """Inject documented fault signatures into copies of normal baseline rows.

    The spikes are large but bounded and the multi-service case is deliberately
    subtle, because a useful comparison must include faults a naive rule misses.
    """
    rng = np.random.default_rng(seed)
    attacks: list[list[float]] = []
    for base in rows:
        for pattern in ATTACK_PATTERNS:
            vector = [float(value) for value in base]
            if pattern == "latency_spike":
                index = FEATURE_NAMES.index("order-service_p95_latency")
                vector[index] = vector[index] * 15 + 0.5 + float(rng.random()) * 0.2
            elif pattern == "error_spike":
                index = FEATURE_NAMES.index("payment-service_error_rate")
                vector[index] = vector[index] + 0.3 + float(rng.random()) * 0.2
            elif pattern == "traffic_drop":
                index = FEATURE_NAMES.index("loadgen_request_rate")
                vector[index] = vector[index] * 0.05
            else:  # subtle_latency: four services rise together, each only a little
                for service in ("cart-service", "order-service", "product-service", "user-service"):
                    index = FEATURE_NAMES.index(f"{service}_p95_latency")
                    vector[index] = vector[index] * 3 + 0.08
            attacks.append(vector)
    return attacks


def _metrics(predicted: Sequence[bool], actual: Sequence[bool]) -> dict:
    """Precision, recall, F1, false-positive rate and accuracy for one detector."""
    tp = sum(1 for p, a in zip(predicted, actual) if p and a)
    fp = sum(1 for p, a in zip(predicted, actual) if p and not a)
    tn = sum(1 for p, a in zip(predicted, actual) if not p and not a)
    fn = sum(1 for p, a in zip(predicted, actual) if not p and a)
    total = max(1, len(actual))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "false_positive_rate": round(fp / (fp + tn) if fp + tn else 0.0, 3),
        "false_positives": fp,
        "false_negatives": fn,
        "accuracy": round((tp + tn) / total, 3),
    }


def compare(
    baseline_path: Path | str = DEFAULT_BASELINE,
    model_path: Path | str = DEFAULT_MODEL,
    seed: int = 7,
) -> dict:
    """Score all three detectors on the same normal + injected-attack dataset."""
    normal = load_baseline(Path(baseline_path))
    attacks = seeded_attacks(normal, seed=seed)
    vectors = list(normal) + attacks
    actual = [False] * len(normal) + [True] * len(attacks)

    detector = Detector.load(Path(model_path))
    mean, std = baseline_stats(normal)

    # 1. Naive 3-sigma rule using the same baseline statistics.
    def rule_based(vector: Sequence[float]) -> bool:
        z = np.abs((np.asarray(vector, dtype=float) - mean) / std)
        return bool(np.max(z) > RULE_Z)

    # 2. Forest score alone; threshold uses the same quantile + margin rule as
    #    Detector.train, which keeps the false-positive comparison like-for-like.
    forest_scores = np.asarray(
        [-detector.forest.score_samples(np.asarray(row, dtype=float).reshape(1, -1))[0]
         for row in normal]
    )
    spread = float(np.std(forest_scores))
    forest_threshold = float(
        np.quantile(forest_scores, 0.99) + max(0.12, 0.25 * spread)
    )

    def forest_only(vector: Sequence[float]) -> bool:
        score = -detector.forest.score_samples(
            np.asarray(vector, dtype=float).reshape(1, -1)
        )[0]
        return bool(score > forest_threshold)

    # 3. The shipped Defender: forest + capped deviation.
    def defender(vector: Sequence[float]) -> bool:
        return detector.is_anomaly(vector)

    results = {}
    for name, predict in (
        ("rule_based_3sigma", rule_based),
        ("isolation_forest_only", forest_only),
        ("defender_forest_plus_deviation", defender),
    ):
        results[name] = _metrics([predict(vector) for vector in vectors], actual)

    return {
        "offline": True,
        "note": "40 recorded normal samples + seeded fault injections; not a live battle",
        "dataset": {
            "normal": len(normal),
            "attacks": len(attacks),
            "features": len(FEATURE_NAMES),
            "seed": seed,
        },
        "detectors": results,
    }


def save_report(report: dict, output: Path | str = DEFAULT_OUTPUT) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path
