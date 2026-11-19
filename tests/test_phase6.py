"""Phase 6 acceptance tests: free workflow, real gate, recomputed from facts."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ci import gate as ci_gate
from ci.gate import check_bundle, load_bundle

ROOT = Path(__file__).resolve().parents[1]
PASSING = ROOT / "ci" / "fixtures" / "passing_battle.json"
FAILING = ROOT / "ci" / "fixtures" / "failing_battle.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


# --------------------------------------------------------------------------- #
# Gate logic
# --------------------------------------------------------------------------- #
def test_load_bundle_reads_battle_facts_only():
    battle = load_bundle(PASSING)
    assert battle.version == "v1.0.3"
    assert battle.attack == "network-latency"
    assert battle.detected is True
    assert battle.cleanup_ok is True


def test_passing_fixture_is_promoted():
    result = check_bundle(PASSING, threshold=70, expect="PROMOTE")
    assert result["passed"] is True
    assert result["verdict"] == "PROMOTE"
    assert result["score"] == 100
    assert result["grade"] == "A"
    assert result["deductions"] == []


def test_failing_fixture_is_blocked():
    result = check_bundle(FAILING, threshold=70, expect="BLOCK")
    assert result["passed"] is True
    assert result["verdict"] == "BLOCK"
    assert result["score"] == 0
    assert result["grade"] == "F"
    assert len(result["deductions"]) == 6


def test_failing_fixture_does_not_pass_a_promote_expectation():
    result = check_bundle(FAILING, threshold=70, expect="PROMOTE")
    assert result["passed"] is False
    assert result["verdict"] == "BLOCK"


def test_stored_decision_is_never_trusted(tmp_path):
    payload = json.loads(FAILING.read_text(encoding="utf-8"))
    payload["decision"]["verdict"] = "PROMOTE"
    payload["decision"]["promote"] = True
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = check_bundle(path, threshold=70, expect="BLOCK")
    assert result["verdict"] == "BLOCK"
    assert result["passed"] is True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_exit_codes_follow_expectation(capsys):
    assert ci_gate.main([
        "check", "--evidence", str(FAILING), "--expect", "BLOCK"
    ]) == 0
    assert "GATE PASSED: BLOCK" in capsys.readouterr().out

    assert ci_gate.main([
        "check", "--evidence", str(FAILING), "--expect", "PROMOTE"
    ]) == 1
    assert "GATE FAILED" in capsys.readouterr().err


def test_guard_reports_no_cluster_and_no_secrets(capsys):
    assert ci_gate.main(["guard"]) == 0
    output = capsys.readouterr().out
    assert '"cluster_required": false' in output
    assert '"secrets_required": []' in output
    assert '"paid_actions_required": false' in output


# --------------------------------------------------------------------------- #
# Workflow file
# --------------------------------------------------------------------------- #
def test_workflow_is_valid_free_and_minimal():
    raw = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    job = data["jobs"]["resilience-gate"]

    assert data["name"] == "ChaosArena Resilience Gate"
    assert data["permissions"] == {"contents": "read"}
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 15

    runs = [step.get("run", "") for step in job["steps"]]
    uses = [step.get("uses", "") for step in job["steps"]]
    assert any("python -m pytest -q" in item for item in runs)
    assert any("python -m ci.gate check" in item for item in runs)
    assert any("npm run build" in item for item in runs)
    assert "actions/checkout@v7.0.1" in uses
    assert "actions/setup-python@v7.1.0" in uses
    assert "actions/setup-node@v7.1.0" in uses

    lowered = raw.lower()
    for banned in ["self-hosted", "aws", "azure", "gcp", "marketplace", "groq_api_key"]:
        assert banned not in lowered


def test_workflow_triggers_push_pr_and_manual():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = data["on"]
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
