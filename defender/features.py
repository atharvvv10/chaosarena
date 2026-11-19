"""The fixed feature layout shared by baseline, model and diagnosis."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SERVICES: tuple[str, ...] = (
    "cart-service",
    "order-service",
    "payment-service",
    "product-service",
    "user-service",
    "loadgen",
)
METRICS: tuple[str, ...] = ("request_rate", "error_rate", "p95_latency")

FEATURE_NAMES: tuple[str, ...] = tuple(
    f"{service}_{metric}" for service in SERVICES for metric in METRICS
)


def vector_from(sample: Mapping[str, Mapping[str, Any]]) -> list[float]:
    """Flatten a sample dict into the fixed, ordered feature vector."""
    vector: list[float] = []
    for service in SERVICES:
        values = sample.get(service, {})
        for metric in METRICS:
            try:
                value = float(values.get(metric, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            vector.append(0.0 if value != value else value)  # drop NaN
    return vector


def empty_sample() -> dict[str, dict[str, float]]:
    return {service: {metric: 0.0 for metric in METRICS} for service in SERVICES}


def feature_position(name: str) -> int:
    return FEATURE_NAMES.index(name)
