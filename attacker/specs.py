"""The seven Phase 2 attacks.

Each attack is a plain Chaos Mesh custom resource. Keeping the definitions as
Python dictionaries makes them easy to test and easy to review: there is no
shell string interpolation and no hidden YAML templates.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .allowlist import (
    ALLOWED_NAMESPACES,
    LABEL_KEY,
    LABEL_VALUE,
    validate_manifest,
    validate_target,
)

NAMESPACE = next(iter(ALLOWED_NAMESPACES))  # always "shop-test"


@dataclass(frozen=True)
class AttackSpec:
    name: str
    kind: str
    action: str
    description: str
    default_target: str
    default_duration: int
    peer: str | None = None


ATTACKS: dict[str, AttackSpec] = {
    spec.name: spec
    for spec in (
        AttackSpec(
            name="pod-kill",
            kind="PodChaos",
            action="pod-kill",
            description="Kill one pod of a service; Kubernetes restarts it.",
            default_target="order-service",
            default_duration=5,
        ),
        AttackSpec(
            name="pod-failure",
            kind="PodChaos",
            action="pod-failure",
            description="Make one pod unavailable for the duration.",
            default_target="cart-service",
            default_duration=30,
        ),
        AttackSpec(
            name="network-latency",
            kind="NetworkChaos",
            action="delay",
            description="Add 300 ms latency to all traffic of a service.",
            default_target="payment-service",
            default_duration=30,
        ),
        AttackSpec(
            name="network-loss",
            kind="NetworkChaos",
            action="loss",
            description="Drop 40% of packets of a service.",
            default_target="order-service",
            default_duration=30,
        ),
        AttackSpec(
            name="network-partition",
            kind="NetworkChaos",
            action="partition",
            description="Cut traffic between two test-namespace services.",
            default_target="order-service",
            default_duration=30,
            peer="product-service",
        ),
        AttackSpec(
            name="cpu-stress",
            kind="StressChaos",
            action="cpu",
            description="Load the CPU of one pod to 80% with two workers.",
            default_target="order-service",
            default_duration=30,
        ),
        AttackSpec(
            name="memory-stress",
            kind="StressChaos",
            action="memory",
            description="Allocate 256 MB in one pod with two workers.",
            default_target="product-service",
            default_duration=30,
        ),
    )
}


def _selector(service: str) -> dict[str, Any]:
    return {"namespaces": [NAMESPACE], "labelSelectors": {"app": service}}


def _spec_for(
    attack: AttackSpec, target: str, duration: int, peer: str
) -> dict[str, Any]:
    """Build the spec section. The allowlist is checked before this runs."""
    duration_text = f"{duration}s"
    selector = _selector(target)

    if attack.name == "pod-kill":
        # pod-kill is a one-shot action; Chaos Mesh ignores a duration here.
        return {"action": "pod-kill", "mode": "one", "selector": selector}

    if attack.name == "pod-failure":
        return {
            "action": "pod-failure",
            "mode": "one",
            "selector": selector,
            "duration": duration_text,
        }

    if attack.name == "network-latency":
        return {
            "action": "delay",
            "mode": "all",
            "selector": selector,
            "direction": "to",
            "delay": {"latency": "300ms", "jitter": "0ms", "correlation": "0"},
            "duration": duration_text,
        }

    if attack.name == "network-loss":
        return {
            "action": "loss",
            "mode": "all",
            "selector": selector,
            "direction": "to",
            "loss": {"loss": "40"},
            "duration": duration_text,
        }

    if attack.name == "network-partition":
        return {
            "action": "partition",
            "mode": "all",
            "selector": selector,
            "direction": "both",
            "target": {"mode": "all", "selector": _selector(peer)},
            "duration": duration_text,
        }

    if attack.name == "cpu-stress":
        return {
            "mode": "one",
            "selector": selector,
            "stressors": {"cpu": {"workers": 2, "load": 80}},
            "duration": duration_text,
        }

    if attack.name == "memory-stress":
        return {
            "mode": "one",
            "selector": selector,
            "stressors": {"memory": {"workers": 2, "size": "256MB"}},
            "duration": duration_text,
        }

    raise ValueError(f"unknown attack {attack.name!r}")  # pragma: no cover


def build_manifest(
    name: str,
    target: str | None = None,
    duration: int | None = None,
    peer: str | None = None,
    suffix: str | None = None,
) -> dict[str, Any]:
    """Build and validate a chaos manifest for one of the seven attacks."""
    try:
        attack = ATTACKS[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown attack {name!r}; choose from {sorted(ATTACKS)}"
        ) from exc

    target = target or attack.default_target
    duration = attack.default_duration if duration is None else int(duration)
    peer = peer or attack.peer or attack.default_target

    if duration <= 0:
        raise ValueError("duration must be a positive number of seconds")

    # Hard boundary: reject prod or unknown services before building anything.
    validate_target(NAMESPACE, target)
    validate_target(NAMESPACE, peer)

    suffix = suffix or uuid.uuid4().hex[:8]
    manifest: dict[str, Any] = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": attack.kind,
        "metadata": {
            "name": f"chaosarena-{attack.name}-{suffix}",
            "namespace": NAMESPACE,
            "labels": {
                LABEL_KEY: LABEL_VALUE,
                "chaosarena.io/attack-name": attack.name,
                "app.kubernetes.io/part-of": "chaosarena",
            },
        },
        "spec": _spec_for(attack, target, duration, peer),
    }

    # Second boundary: validate the finished object, not just the inputs.
    validate_manifest(manifest)
    return manifest
