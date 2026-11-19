"""Bounded remedial actions the defender is allowed to take.

The defender can restart or scale a deployment in shop-test. It cannot delete
anything, touch shop-prod, or change replica counts beyond MAX_REPLICAS.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import kubectl as k8s

ALLOWED_NAMESPACE = "shop-test"
ALLOWED_SERVICES: frozenset[str] = frozenset(
    {
        "user-service",
        "product-service",
        "cart-service",
        "order-service",
        "payment-service",
        "loadgen",
    }
)
MIN_REPLICAS = 1
MAX_REPLICAS = 4
ACTION_LOG = Path("ml/defender_actions.jsonl")


class ActionRejected(ValueError):
    """Raised for any action outside the defender's hard allowlist."""


def validate_service(service: str) -> None:
    if service not in ALLOWED_SERVICES:
        raise ActionRejected(
            f"service {service!r} is not allowed; permitted: {sorted(ALLOWED_SERVICES)}"
        )


def _record(action: str, service: str, details: dict[str, object]) -> dict[str, object]:
    entry: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "namespace": ALLOWED_NAMESPACE,
        "action": action,
        "service": service,
        **details,
    }
    ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACTION_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def restart(service: str) -> dict[str, object]:
    validate_service(service)
    k8s.run(["-n", ALLOWED_NAMESPACE, "rollout", "restart", f"deploy/{service}"])
    k8s.run(
        [
            "-n", ALLOWED_NAMESPACE, "rollout", "status",
            f"deploy/{service}", "--timeout=120s",
        ],
        check=False,
    )
    return _record("restart", service, {"status": "requested"})


def scale(service: str, replicas: int) -> dict[str, object]:
    validate_service(service)
    bounded = max(MIN_REPLICAS, min(MAX_REPLICAS, int(replicas)))
    k8s.run(
        [
            "-n", ALLOWED_NAMESPACE, "scale",
            f"deploy/{service}", f"--replicas={bounded}",
        ]
    )
    return _record("scale", service, {"requested": replicas, "applied": bounded})


def apply(action: str, service: str, replicas: int | None = None) -> dict[str, object]:
    if action == "restart":
        return restart(service)
    if action == "scale":
        if replicas is None:
            raise ValueError("scale requires --replicas")
        return scale(service, replicas)
    raise ActionRejected(f"unknown action {action!r}")
