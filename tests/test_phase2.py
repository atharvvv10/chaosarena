"""Phase 2 acceptance tests: allowlist, 7 attacks, and guaranteed cleanup."""
from __future__ import annotations

import pytest

from attacker import kubectl as k8s
from attacker import runner as runner_module
from attacker.allowlist import (
    LABEL_KEY,
    LABEL_VALUE,
    AttackRejected,
    validate_manifest,
    validate_target,
)
from attacker.runner import ChaosRunner
from attacker.specs import ATTACKS, build_manifest


# --------------------------------------------------------------------------- #
# Hard allowlist
# --------------------------------------------------------------------------- #
def test_allowlist_rejects_prod_namespace():
    with pytest.raises(AttackRejected, match="shop-prod"):
        validate_target("shop-prod", "order-service")


def test_allowlist_rejects_unknown_service():
    with pytest.raises(AttackRejected, match="evil-service"):
        validate_target("shop-test", "evil-service")


def test_allowlist_rejects_manifest_without_cleanup_label():
    manifest = build_manifest("pod-kill", suffix="test")
    del manifest["metadata"]["labels"][LABEL_KEY]
    with pytest.raises(AttackRejected, match=LABEL_KEY):
        validate_manifest(manifest)


def test_allowlist_rejects_prod_selector_namespace():
    manifest = build_manifest("pod-kill", suffix="test")
    manifest["spec"]["selector"]["namespaces"] = ["shop-prod"]
    with pytest.raises(AttackRejected, match="shop-prod"):
        validate_manifest(manifest)


# --------------------------------------------------------------------------- #
# Seven attacks
# --------------------------------------------------------------------------- #
def test_seven_attacks_are_defined():
    assert set(ATTACKS) == {
        "pod-kill",
        "pod-failure",
        "network-latency",
        "network-loss",
        "network-partition",
        "cpu-stress",
        "memory-stress",
    }


@pytest.mark.parametrize("name", sorted(ATTACKS))
def test_every_attack_builds_a_valid_manifest(name):
    manifest = build_manifest(name, suffix="test")
    assert manifest["metadata"]["namespace"] == "shop-test"
    assert manifest["metadata"]["labels"][LABEL_KEY] == LABEL_VALUE
    validate_manifest(manifest)


def test_attack_parameters_are_present():
    latency = build_manifest("network-latency", suffix="test")
    assert latency["spec"]["delay"]["latency"] == "300ms"
    assert latency["spec"]["duration"] == "30s"

    loss = build_manifest("network-loss", suffix="test")
    assert loss["spec"]["loss"]["loss"] == "40"

    partition = build_manifest("network-partition", suffix="test", peer="cart-service")
    assert partition["spec"]["target"]["selector"]["labelSelectors"]["app"] == "cart-service"

    cpu = build_manifest("cpu-stress", suffix="test")
    assert cpu["spec"]["stressors"]["cpu"]["load"] == 80

    memory = build_manifest("memory-stress", suffix="test")
    assert memory["spec"]["stressors"]["memory"]["size"] == "256MB"


def test_unknown_or_prod_target_cannot_be_built():
    with pytest.raises(ValueError, match="unknown attack"):
        build_manifest("does-not-exist")
    with pytest.raises(AttackRejected):
        build_manifest("pod-kill", target="prod-service")
    with pytest.raises(AttackRejected):
        build_manifest("network-partition", peer="outside-service")


# --------------------------------------------------------------------------- #
# Guaranteed cleanup
# --------------------------------------------------------------------------- #
def test_cleanup_runs_when_apply_fails(monkeypatch):
    calls: list[str] = []

    def fail_apply(_manifest):
        calls.append("apply")
        raise RuntimeError("apply exploded")

    monkeypatch.setattr(k8s, "apply_manifest", fail_apply)
    monkeypatch.setattr(k8s, "active_names", lambda *_: ["podchaos/chaosarena-x"])
    monkeypatch.setattr(k8s, "delete_names", lambda names, ns: calls.append(f"deleted:{names[0]}") or names)
    monkeypatch.setattr(runner_module.time, "sleep", lambda _: None)

    result = ChaosRunner().launch("pod-kill", hold=0)

    assert calls == ["apply", "deleted:podchaos/chaosarena-x"]
    assert result.cleanup_ok is True
    assert "apply exploded" in result.error
    assert result.ok is False


def test_cleanup_runs_when_sleep_is_interrupted(monkeypatch):
    calls: list[str] = []

    def interrupt(_seconds):
        calls.append("sleep")
        raise KeyboardInterrupt()

    monkeypatch.setattr(k8s, "apply_manifest", lambda _: calls.append("apply"))
    monkeypatch.setattr(runner_module.time, "sleep", interrupt)
    monkeypatch.setattr(k8s, "active_names", lambda *_: ["networkchaos/chaosarena-y"])
    monkeypatch.setattr(k8s, "delete_names", lambda names, ns: calls.append("cleanup") or names)

    # KeyboardInterrupt is a BaseException: the finally block must still clean up.
    with pytest.raises(KeyboardInterrupt):
        ChaosRunner().launch("network-latency", hold=1)

    assert calls == ["apply", "sleep", "cleanup"]


def test_cleanup_deletes_only_labelled_objects(monkeypatch):
    seen: list[tuple[str, str]] = []

    def fake_active(namespace, selector):
        seen.append((namespace, selector))
        return ["stresschaos/chaosarena-z"]

    monkeypatch.setattr(k8s, "active_names", fake_active)
    monkeypatch.setattr(k8s, "delete_names", lambda names, ns: names)

    deleted = ChaosRunner().cleanup()

    assert deleted == ["stresschaos/chaosarena-z"]
    assert seen == [("shop-test", "chaosarena.io/attack=true")]


def test_runner_never_accepts_prod_namespace():
    with pytest.raises(AttackRejected, match="shop-prod"):
        ChaosRunner("shop-prod")
