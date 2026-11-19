"""Phase 3 acceptance tests: Isolation Forest, diagnosis, bounded actions."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from defender import actions, collect, model, verify
from defender.actions import ActionRejected
from defender.diagnose import diagnose
from defender.features import FEATURE_NAMES, SERVICES, vector_from
from defender.model import Detector, baseline_stats
from defender.policy import choose_action
from defender.verify import verify as verify_score


def _normal_values() -> list[float]:
    """A realistic, stable baseline: traffic, errors and latency per service."""
    return [
        2.0 if index % 3 == 0 else (0.01 if index % 3 == 1 else 0.2)
        for index in range(len(FEATURE_NAMES))
    ]


def _baseline_rows(count: int = 30, noise: float = 0.01) -> list[list[float]]:
    rng = np.random.default_rng(7)
    base = np.asarray(_normal_values(), dtype=float)
    return (base + rng.normal(0.0, noise, size=(count, len(FEATURE_NAMES)))).tolist()


def _normal_sample() -> dict[str, dict[str, float]]:
    values = _normal_values()
    sample: dict[str, dict[str, float]] = {}
    for index, service in enumerate(SERVICES):
        sample[service] = {
            "request_rate": values[index * 3],
            "error_rate": values[index * 3 + 1],
            "p95_latency": values[index * 3 + 2],
        }
    return sample


# --------------------------------------------------------------------------- #
# Feature layout
# --------------------------------------------------------------------------- #
def test_feature_layout_is_fixed():
    assert len(FEATURE_NAMES) == 18
    assert FEATURE_NAMES[0] == "cart-service_request_rate"
    assert FEATURE_NAMES[-1] == "loadgen_p95_latency"


def test_vector_from_fills_missing_and_nan():
    sample = {"order-service": {"request_rate": 2.5, "p95_latency": float("nan")}}
    vector = vector_from(sample)
    assert len(vector) == 18
    assert vector[FEATURE_NAMES.index("order-service_request_rate")] == 2.5
    assert vector[FEATURE_NAMES.index("order-service_p95_latency")] == 0.0
    assert vector[FEATURE_NAMES.index("cart-service_request_rate")] == 0.0


# --------------------------------------------------------------------------- #
# Detection model
# --------------------------------------------------------------------------- #
def test_detector_trains_and_flags_an_anomaly():
    rows = _baseline_rows()
    detector = Detector.train(rows)
    normal = vector_from(_normal_sample())
    attack = vector_from(_normal_sample())
    attack[FEATURE_NAMES.index("order-service_p95_latency")] = 5.0

    assert detector.score(normal) <= detector.threshold
    assert detector.score(attack) > detector.threshold
    assert detector.is_anomaly(attack) is True
    assert detector.is_anomaly(normal) is False


def test_detector_save_load_roundtrip(tmp_path):
    detector = Detector.train(_baseline_rows())
    path = detector.save(tmp_path / "model.joblib")
    loaded = Detector.load(path)
    vector = vector_from({"payment-service": {"p95_latency": 0.02}})
    assert loaded.threshold == pytest.approx(detector.threshold)
    assert loaded.score(vector) == pytest.approx(detector.score(vector))


def test_detector_rejects_too_little_training_data():
    with pytest.raises(ValueError, match="at least 5 rows"):
        Detector.train([[0.0] * 18] * 3)


def test_baseline_csv_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "sample_once", lambda *_: {"order-service": {"request_rate": 1.0}})
    monkeypatch.setattr(collect.time, "sleep", lambda _: None)
    path = collect.collect_baseline(samples=6, interval=0, output=tmp_path / "baseline.csv")
    rows = collect.load_baseline(path)
    assert len(rows) == 6
    assert all(len(row) == 18 for row in rows)


# --------------------------------------------------------------------------- #
# Diagnosis and policy
# --------------------------------------------------------------------------- #
def test_diagnosis_identifies_latency_spike():
    rows = _baseline_rows()
    mean, std = baseline_stats(rows)
    attack = vector_from(_normal_sample())
    attack[FEATURE_NAMES.index("payment-service_p95_latency")] = 4.0
    result = diagnose(attack, mean, std)
    assert result.category == "latency_spike"
    assert result.service == "payment-service"
    assert result.confidence > 0.5
    assert any("payment-service_p95_latency" in item for item in result.evidence)


def test_diagnosis_identifies_error_spike_and_traffic_drop():
    rows = _baseline_rows()
    mean, std = baseline_stats(rows)
    errors_vector = vector_from(_normal_sample())
    errors_vector[FEATURE_NAMES.index("cart-service_error_rate")] = 3.0
    drop_vector = vector_from(_normal_sample())
    drop_vector[FEATURE_NAMES.index("loadgen_request_rate")] = -3.0
    errors = diagnose(errors_vector, mean, std)
    drop = diagnose(drop_vector, mean, std)
    assert errors.category == "error_spike"
    assert drop.category == "traffic_drop"


def test_policy_maps_categories_to_bounded_actions():
    rows = _baseline_rows()
    mean, std = baseline_stats(rows)
    latency_vector = vector_from(_normal_sample())
    latency_vector[FEATURE_NAMES.index("order-service_p95_latency")] = 4.0
    drop_vector = vector_from(_normal_sample())
    drop_vector[FEATURE_NAMES.index("loadgen_request_rate")] = -3.0
    latency = diagnose(latency_vector, mean, std)
    drop = diagnose(drop_vector, mean, std)
    assert choose_action(latency) == {"action": "restart", "service": "order-service"}
    assert choose_action(drop) == {"action": "scale", "service": "loadgen", "replicas": 3}


# --------------------------------------------------------------------------- #
# Bounded actions
# --------------------------------------------------------------------------- #
def test_action_allowlist_rejects_unknown_service_and_actions():
    with pytest.raises(ActionRejected, match="not allowed"):
        actions.restart("prod-service")
    with pytest.raises(ActionRejected, match="unknown action"):
        actions.apply("delete", "order-service")
    assert actions.ALLOWED_NAMESPACE == "shop-test"


def test_scale_is_clamped_and_logged(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(actions.k8s, "run", lambda args, **_: calls.append(args))
    monkeypatch.setattr(actions, "ACTION_LOG", tmp_path / "actions.jsonl")

    entry = actions.scale("cart-service", 99)

    assert entry["applied"] == actions.MAX_REPLICAS
    assert entry["namespace"] == "shop-test"
    assert calls[0][-1] == f"--replicas={actions.MAX_REPLICAS}"
    assert (tmp_path / "actions.jsonl").exists()


def test_restart_targets_only_test_namespace(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(actions.k8s, "run", lambda args, **_: calls.append(args))
    monkeypatch.setattr(actions, "ACTION_LOG", tmp_path / "actions.jsonl")
    actions.restart("order-service")
    assert calls[0] == ["-n", "shop-test", "rollout", "restart", "deploy/order-service"]


# --------------------------------------------------------------------------- #
# Verify and isolation
# --------------------------------------------------------------------------- #
def test_verify_reports_recovery(monkeypatch):
    detector = Detector.train(_baseline_rows())
    normal = vector_from(_normal_sample())
    attack = vector_from(_normal_sample())
    attack[FEATURE_NAMES.index("order-service_p95_latency")] = 5.0
    monkeypatch.setattr(verify.time, "sleep", lambda _: None)
    sampler = _normal_sample

    result = verify_score(detector, attack, wait=0, sampler=sampler)
    assert result.recovered is True
    assert result.score_before > result.threshold
    assert result.score_after <= result.threshold
    assert detector.score(normal) <= detector.threshold
    assert result.score_after == pytest.approx(detector.score(normal))


def test_defender_does_not_import_attacker():
    root = Path(__file__).resolve().parents[1] / "defender"
    for source in root.glob("*.py"):
        text = source.read_text(encoding="utf-8").lower()
        assert "import attacker" not in text
        assert "from attacker" not in text
