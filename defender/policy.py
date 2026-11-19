"""Simple, reviewable mapping from diagnosis to bounded action."""
from __future__ import annotations

from .diagnose import Diagnosis


def choose_action(diagnosis: Diagnosis) -> dict[str, object]:
    if diagnosis.category in {"latency_spike", "error_spike"}:
        return {"action": "restart", "service": diagnosis.service}
    if diagnosis.category == "traffic_drop":
        return {"action": "scale", "service": diagnosis.service, "replicas": 3}
    return {"action": "none", "service": diagnosis.service}
