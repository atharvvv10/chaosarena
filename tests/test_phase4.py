"""Phase 4 acceptance tests: score, gate, decision log and CLI-only isolation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controller import api
from controller.battle import BattleRunner, ControllerError
from controller.gate import evaluate_gate, last_decision, record_decision
from controller.score import BattleResult, score_battle


def _perfect() -> BattleResult:
    return BattleResult(
        attack="network-latency",
        target="payment-service",
        version="v1.0.1",
        detected=True,
        detection_seconds=9.5,
        recovered=True,
        final_score=0.56,
        defender_threshold=0.74,
        cleanup_ok=True,
        chaos_objects_remaining=0,
        diagnosis={"category": "latency_spike", "service": "order-service"},
        action_taken={"action": "restart", "service": "order-service"},
        attack_error=None,
    )


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def test_perfect_battle_scores_100():
    scored = score_battle(_perfect())
    assert scored.score == 100
    assert scored.grade == "A"
    assert scored.deductions == []


def test_score_deductions_are_explained():
    result = _perfect()
    result.detected = False
    result.recovered = False
    result.cleanup_ok = False
    result.chaos_objects_remaining = 2
    result.final_score = 0.9
    result.attack_error = "boom"

    scored = score_battle(result)

    assert scored.score == 0
    assert len(scored.deductions) == 6
    assert any("never detected" in item for item in scored.deductions)
    assert any("cleanup failed" in item for item in scored.deductions)
    assert any("chaos objects" in item for item in scored.deductions)


def test_slow_detection_is_penalised():
    result = _perfect()
    result.detection_seconds = 25.0
    scored = score_battle(result)
    assert scored.score == 85
    assert scored.grade == "B"


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #
def test_gate_promotes_a_good_battle():
    result = _perfect()
    decision = evaluate_gate(result, score_battle(result), threshold=70)
    assert decision.promote is True
    assert decision.verdict == "PROMOTE"
    assert any("meets threshold" in reason for reason in decision.reasons)


def test_gate_blocks_a_low_score_even_with_clean_cleanup():
    result = _perfect()
    result.detected = False
    result.recovered = False
    decision = evaluate_gate(result, score_battle(result), threshold=70)
    assert decision.promote is False
    assert decision.verdict == "BLOCK"
    assert decision.score < 70


def test_gate_blocks_unsafe_cleanup_regardless_of_score():
    result = _perfect()
    scored = score_battle(result)
    result.cleanup_ok = False
    result.chaos_objects_remaining = 1
    decision = evaluate_gate(result, scored, threshold=70)
    assert decision.promote is False
    assert any("cleanup failed" in reason for reason in decision.reasons)
    assert any("left behind" in reason for reason in decision.reasons)


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #
def test_decision_log_appends_and_reads_last(tmp_path):
    path = tmp_path / "decisions.jsonl"
    assert last_decision(path) is None

    result = _perfect()
    first = evaluate_gate(result, score_battle(result))
    second = evaluate_gate(result, score_battle(result))
    record_decision(first, path)
    record_decision(second, path)

    saved = last_decision(path)
    assert saved["verdict"] == "PROMOTE"
    assert len([line for line in path.read_text(encoding="utf-8").splitlines() if line]) == 2


# --------------------------------------------------------------------------- #
# Isolation and boundaries
# --------------------------------------------------------------------------- #
def test_controller_does_not_import_attacker_or_defender():
    root = Path(__file__).resolve().parents[1] / "controller"
    for source in root.glob("*.py"):
        text = source.read_text(encoding="utf-8").lower()
        assert "import attacker" not in text
        assert "from attacker" not in text
        assert "import defender" not in text
        assert "from defender" not in text


def test_battle_runner_rejects_unknown_attack():
    with pytest.raises(ControllerError, match="unknown attack"):
        BattleRunner().run(attack="delete-everything")


def test_health_endpoint():
    client = TestClient(api.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_score_cli_uses_saved_result(tmp_path):
    payload = _perfect().as_dict()
    path = tmp_path / "battle.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scored = score_battle(BattleResult(**json.loads(path.read_text(encoding="utf-8"))))
    assert scored.score == 100
