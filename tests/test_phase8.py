"""Phase 8 acceptance tests: free tabular RL attacker, sim and real paths."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from attacker.allowlist import ALLOWED_SERVICES
from controller.battle import KNOWN_ATTACKS
from rl import benchmark as rl_benchmark
from rl import cli as rl_cli
from rl.agent import QLearningAgent
from rl.arena import (
    ACTION_SPACE,
    REAL_ACTION_ALLOWLIST,
    Action,
    ArenaError,
    RealArena,
    SimArena,
)

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #
def test_action_space_uses_only_known_attacks_and_allowed_services():
    assert len(ACTION_SPACE) == 7
    for action in ACTION_SPACE:
        assert action.attack in KNOWN_ATTACKS
        assert action.target in ALLOWED_SERVICES
        assert action.duration > 0

    assert all("shop-prod" not in action.key for action in ACTION_SPACE)
    assert all("production" not in action.key for action in ACTION_SPACE)


def test_real_allowlist_is_a_strict_subset_of_action_space():
    keys = {action.key for action in ACTION_SPACE}
    assert REAL_ACTION_ALLOWLIST <= keys
    assert len(REAL_ACTION_ALLOWLIST) < len(keys)


def test_real_arena_rejects_unproven_action():
    action = Action("network-partition", "order-service")
    assert action.key not in REAL_ACTION_ALLOWLIST
    with pytest.raises(ArenaError, match="refuses unproven action"):
        RealArena().validate(action)


def test_guard_reports_free_local_boundaries(capsys):
    assert rl_cli.main(["guard"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed_namespaces"] == ["shop-test"]
    assert payload["simulation_needs_cluster"] is False
    assert payload["real_interface"] == "controller.cli"
    assert payload["imports_kubernetes_directly"] is False
    assert payload["paid_dependencies"] == []


def test_no_paid_or_cloud_dependencies_added():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "rl").glob("*.py"))
    )
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    combined = (sources + "\n" + requirements).lower()
    for banned in ["torch", "tensorflow", "openai", "groq", "aws", "azure", "gcp", "gym"]:
        assert banned not in combined


# --------------------------------------------------------------------------- #
# Simulator + Q-learning
# --------------------------------------------------------------------------- #
def test_sim_arena_reward_is_damage_to_resilience_score():
    arena = SimArena()
    result = arena.step(Action("network-partition", "payment-service"))
    assert result.score == 70
    assert result.reward == pytest.approx(0.3)
    assert result.state == "alert"
    assert result.detail["simulated"] is True

    good = arena.step(Action("network-latency", "payment-service"))
    assert good.score == 100
    assert good.reward == 0.0
    assert good.state == "calm"


def test_q_learning_prefers_the_weakest_defender_matchup():
    agent = rl_cli.train_agent(episodes=40, seed=7)
    best = agent.best_action("calm")
    assert best.attack == "network-partition"
    assert agent.q["calm"][best.key] > 0.5
    assert agent.epsilon < 1.0


def test_learned_attacker_does_more_damage_than_random():
    agent = rl_cli.train_agent(episodes=200, seed=7)
    agent.epsilon = 0.0
    report = rl_benchmark.compare(agent, episodes=200, seed=7)
    assert report["simulated"] is True
    assert report["learned_does_more_damage"] is True
    assert report["damage_ratio"] > 1.5
    assert report["learned"]["avg_resilience_score"] < report["random"]["avg_resilience_score"]
    assert report["learned"]["best_action"] == "network-partition@payment-service"


def test_rl_benchmark_cli_writes_committed_evidence(tmp_path, capsys):
    table = tmp_path / "q.json"
    output = tmp_path / "benchmark.json"
    rl_cli.train_agent(episodes=200, seed=7).save(table)
    assert rl_cli.main([
        "benchmark", "--table", str(table), "--output", str(output)
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["saved"] == str(output)
    assert payload["learned_does_more_damage"] is True
    assert output.exists()


def test_training_is_deterministic_with_a_seed():
    first = rl_cli.train_agent(episodes=20, seed=11)
    second = rl_cli.train_agent(episodes=20, seed=11)
    assert first.q == second.q
    assert first.epsilon == second.epsilon


def test_epsilon_decays_but_never_disappears():
    agent = QLearningAgent(epsilon=1.0, epsilon_decay=0.5, epsilon_min=0.1)
    agent.decay()
    assert agent.epsilon == 0.5
    for _ in range(20):
        agent.decay()
    assert agent.epsilon == 0.1


def test_q_table_round_trip(tmp_path):
    agent = rl_cli.train_agent(episodes=10, seed=3)
    path = agent.save(tmp_path / "q.json")
    loaded = QLearningAgent.load(path)
    assert loaded.q == agent.q
    assert loaded.gamma == agent.gamma


def test_train_cli_writes_committed_evidence(tmp_path, capsys):
    output = tmp_path / "q.json"
    assert rl_cli.main(["train", "--episodes", "5", "--seed", "1", "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["saved"] == str(output)
    assert output.exists()


def test_policy_cli_reports_learned_ranking(tmp_path, capsys):
    agent = rl_cli.train_agent(episodes=10, seed=2)
    table = agent.save(tmp_path / "q.json")
    assert rl_cli.main(["policy", "--table", str(table)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "calm" in payload["policy"]
    assert payload["policy"]["calm"][0]["q"] >= payload["policy"]["calm"][-1]["q"]


# --------------------------------------------------------------------------- #
# Real path (mocked subprocess — no cluster in tests)
# --------------------------------------------------------------------------- #
def _fake_payload(score: int = 70, detected: bool = False) -> str:
    return json.dumps({
        "battle": {"detected": detected, "attack": "pod-kill", "target": "order-service"},
        "score": {"score": score, "deductions": ["fault was never detected (-30)"]},
        "decision": {"verdict": "PROMOTE"},
    })


def test_real_arena_calls_public_controller_cli(monkeypatch):
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=_fake_payload(), stderr="")

    monkeypatch.setattr("rl.arena.subprocess.run", fake_run)
    action = Action("pod-kill", "order-service")
    result = RealArena(duration=10, settle=20, threshold=0).step(action, version="rl-test")

    command = captured["command"]
    assert command[1:3] == ["-m", "controller.cli"]
    assert command[3] == "evaluate"
    assert command[5] == "pod-kill"
    assert command[7] == "order-service"
    assert "--duration" in command and "10" in command
    assert "--threshold" in command and "0" in command
    assert "--settle" in command and "20" in command
    assert captured["kwargs"]["cwd"] == ROOT
    assert result.score == 70
    assert result.reward == pytest.approx(0.3)
    assert result.state == "alert"
    assert result.detail["verdict"] == "PROMOTE"


def test_real_cli_dry_run_never_runs_a_battle(tmp_path, monkeypatch, capsys):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("dry-run must not execute a battle")

    monkeypatch.setattr("rl.arena.subprocess.run", fail_if_called)
    table = tmp_path / "q.json"
    rl_cli.train_agent(episodes=5, seed=4).save(table)

    assert rl_cli.main([
        "real", "--table", str(table), "--dry-run", "--episodes", "2"
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["runs"]) == 2
    assert all(run["dry_run"] is True for run in payload["runs"])
    assert all(run["command"][2] == "controller.cli" for run in payload["runs"])
    assert all(run["action"] in REAL_ACTION_ALLOWLIST for run in payload["runs"])


def test_real_cli_updates_q_table_from_real_reward(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "rl.arena.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=0, stdout=_fake_payload(), stderr=""),
    )
    table = tmp_path / "q.json"
    agent = rl_cli.train_agent(episodes=5, seed=5)
    before = agent.q["calm"]["pod-kill@order-service"]
    agent.save(table)

    assert rl_cli.main(["real", "--table", str(table), "--episodes", "1"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runs"][0]["score"] == 70
    assert payload["runs"][0]["reward"] == pytest.approx(0.3)

    updated = QLearningAgent.load(table)
    assert updated.q["calm"]["pod-kill@order-service"] > before


def test_real_cli_reports_controller_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "rl.arena.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="cluster down"),
    )
    table = tmp_path / "q.json"
    rl_cli.train_agent(episodes=5, seed=6).save(table)

    assert rl_cli.main(["real", "--table", str(table), "--episodes", "1"]) == 1
    assert "no JSON" in capsys.readouterr().err
