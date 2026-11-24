"""Tests for the offline v1.2 comparison harness."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("torch")

from scripts.deep_validation import compare_attackers, compare_defenders

ROOT = Path(__file__).resolve().parents[1]


def test_deep_attacker_summary_reports_simulator_wins_without_p_value():
    payload = compare_attackers(episodes=10)
    summary = payload["seeded_simulator_wins"]
    assert summary["episodes"] == 10
    assert summary["deep_better"] > 0
    assert "two_sided_p" not in summary
    assert "p_value" not in payload["note"]


def test_attacker_comparison_reports_a_deep_win():
    payload = compare_attackers(episodes=10)
    assert payload["deep"]["mean_reward"] > payload["tabular"]["mean_reward"]
    assert payload["seeded_simulator_wins"]["deep_better"] > 0


def test_defender_comparison_reports_all_four_detectors():
    payload = compare_defenders(samples=3, epochs=5)
    for name in ("neural", "defender_shipped", "rule_based_3sigma", "isolation_forest"):
        assert name in payload
        assert payload[name]["detections"] >= 0
        assert payload[name]["false_alarms"] >= 0
    assert payload["neural"]["threshold"] > 0


def test_committed_validation_file_is_well_formed():
    payload = json.loads(open("ml/deep/validation.json", encoding="utf-8").read())
    assert payload["version"] == "v1.2-deep-aiml"
    assert "seeded_simulator_wins" in payload["attacker"]
    assert "two_sided_p" not in json.dumps(payload)
    for name in ("neural", "defender_shipped", "rule_based_3sigma", "isolation_forest"):
        assert name in payload["defender"]

    architecture = (ROOT / "docs" / "ARCHITECTURE_AIML.md").read_text(encoding="utf-8")
    assert "2e-09" not in architecture
    assert "Work in progress" not in architecture
    assert "Rule-based (3-sigma)" in architecture
    assert "Shipped Defender" in architecture

    live = (ROOT / "docs" / "V12_LIVE_VALIDATION.md").read_text(encoding="utf-8")
    assert "on the `v1.2-deep-aiml` branch" not in live
    assert "false negative" in live
    assert "self-heals" in live

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "p ≈ 2e-09" not in readme
    assert "false negative" in readme
    assert "detector drift" in readme
