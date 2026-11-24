"""Tests for the offline v1.2 comparison harness."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("torch")

from scripts.deep_validation import compare_attackers, compare_defenders, exact_sign_test


def test_exact_sign_test_matches_reference_value():
    result = exact_sign_test(8, 2)
    assert result["n"] == 10
    assert result["two_sided_p"] == pytest.approx(0.109375)


def test_attacker_comparison_reports_a_deep_win():
    payload = compare_attackers(episodes=10)
    assert payload["deep"]["mean_reward"] > payload["tabular"]["mean_reward"]
    assert payload["sign_test_deep_better"]["positive"] > 0


def test_defender_comparison_reports_both_models():
    payload = compare_defenders(samples=3, epochs=5)
    assert payload["neural"]["detections"] >= 0
    assert payload["isolation_forest"]["false_alarms"] >= 0
    assert payload["neural"]["threshold"] > 0


def test_committed_validation_file_is_well_formed():
    payload = json.loads(open("ml/deep/validation.json", encoding="utf-8").read())
    assert payload["version"] == "v1.2-deep-aiml"
    assert "sign_test_deep_better" in payload["attacker"]
    assert "neural" in payload["defender"]
