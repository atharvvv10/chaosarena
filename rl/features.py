"""Numeric state encoding for the deep RL attacker.

The tabular agent only sees ``"calm"`` or ``"alert"``. The deep agent sees a
fixed 10-value vector built from the *same* battle facts, so it can distinguish
a barely-detected expensive attack from a cheap clean one.
"""
from __future__ import annotations

from collections.abc import Mapping

from .arena import ACTION_SPACE, Action, StepResult

STATE_DIM = 10

_TARGET_WEIGHT = {
    "payment-service": 1.0,
    "order-service": 0.9,
    "cart-service": 0.7,
    "product-service": 0.6,
    "user-service": 0.5,
    "loadgen": 0.3,
}


def _unit(value: float) -> float:
    """Clamp to [0, 1] so every network input has the same scale."""
    return round(max(0.0, min(1.0, value)), 6)


def encode(
    result: StepResult | None,
    action: Action | None,
    step: int = 0,
    epsilon: float = 0.0,
    max_steps: int = 100,
) -> list[float]:
    """Encode a battle step into the fixed-length vector the DQN expects."""
    detail: Mapping[str, object] = result.detail if result is not None else {}
    score = float(result.score) / 100.0 if result is not None else 0.0
    detected = 1.0 if result is not None and result.detected else 0.0
    alert = 1.0 if result is not None and result.state == "alert" else 0.0
    reward = float(result.reward) if result is not None else 0.0
    action_index = (
        ACTION_SPACE.index(action) / max(1, len(ACTION_SPACE) - 1)
        if action is not None
        else 0.0
    )
    anomaly = float(detail.get("anomaly_score", 0.0) or 0.0)
    target_weight = _TARGET_WEIGHT.get(action.target, 0.4) if action is not None else 0.0

    return [
        _unit(score),
        _unit(detected),
        _unit(alert),
        _unit((reward + 1.0) / 2.0),
        _unit(action_index),
        _unit(step / max(1, max_steps)),
        _unit(epsilon),
        _unit(1.0 - score),
        _unit(target_weight),
        _unit(anomaly),
    ]
