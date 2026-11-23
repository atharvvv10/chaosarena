"""Regression tests for the final correctness fixes."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from controller import api
from controller import battle as battle_module
from controller.battle import ControllerError, BattleRunner, recovery_confirmed
from controller.score import BattleResult

ROOT = Path(__file__).resolve().parents[1]


def _perfect() -> BattleResult:
    return BattleResult(
        attack="network-latency",
        target="payment-service",
        version="v9.9.9",
        detected=True,
        detection_seconds=9.5,
        recovered=True,
        final_score=0.56,
        defender_threshold=0.74,
        cleanup_ok=True,
        chaos_objects_remaining=0,
        diagnosis={"category": "latency_spike", "service": "order-service"},
        action_taken={"action": "restart", "service": "order-service"},
    )


def test_recovery_requires_normal_final_measurement():
    assert recovery_confirmed({"score": 0.56, "anomaly": False}, 0.74) is True
    assert recovery_confirmed({"score": 0.81, "anomaly": False}, 0.74) is False
    assert recovery_confirmed({"score": 0.56, "anomaly": True}, 0.74) is False


def test_missing_or_invalid_final_measurements_never_confirm_recovery():
    valid = {"score": 0.56, "anomaly": False}
    invalid = [
        {},
        {"score": 0.56},
        {"anomaly": False},
        {"score": "not-a-number", "anomaly": False},
        {"score": float("nan"), "anomaly": False},
        {"score": float("inf"), "anomaly": False},
        {"score": True, "anomaly": False},
        {"score": 0.56, "anomaly": "false"},
        {"score": 0.56, "anomaly": None},
        None,
    ]

    assert recovery_confirmed(valid, 0.74) is True
    for final in invalid:
        assert recovery_confirmed(final, 0.74) is False


def test_earlier_verification_cannot_override_abnormal_final_measurement(
    monkeypatch, tmp_path
):
    detections = iter(
        [
            {"score": 0.3, "threshold": 0.7, "anomaly": False},
            {"score": 0.9, "threshold": 0.7, "anomaly": True},
            {"score": 0.8, "threshold": 0.7, "anomaly": True},
        ]
    )
    verification_calls: list[dict] = []

    def fake_run_cli(module: str, *args: str, **kwargs: object) -> dict:
        if module == "attacker.cli" and args[0] == "status":
            return {"chaos_objects": []}
        if module == "defender.cli" and args[0] == "detect":
            return next(detections)
        if module == "defender.cli" and args[0] == "run":
            verification_calls.append({"recovered": True})
            return {"verification": {"recovered": True}}
        raise AssertionError(f"unexpected CLI call: {module} {args}")

    class FakeProcess:
        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls == 1 else 0

        def wait(self) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        handle = kwargs["stdout"]
        handle.write(json.dumps({"ok": True, "cleanup_ok": True}) + "\n")
        return FakeProcess()

    monkeypatch.setattr(battle_module, "run_cli", fake_run_cli)
    monkeypatch.setattr(battle_module.subprocess, "Popen", fake_popen)

    runner = BattleRunner(
        poll_interval=0.01,
        defender_wait=1.0,
        settle_seconds=0,
        startup_settle_seconds=0,
        log_path=tmp_path / "last_attack.json",
    )
    result = runner.run()

    assert verification_calls == [{"recovered": True}]
    assert result.detected is True
    assert result.recovered is False
    assert result.final_score == 0.8
    assert result.recovery_seconds is None


def test_new_evaluation_refreshes_the_incident_report(monkeypatch, tmp_path):
    result = _perfect()
    result.attack = "pod-kill"
    report_path = tmp_path / "incident_report.md"

    monkeypatch.setattr(api, "REPORT_FILE", report_path)
    monkeypatch.setattr(
        api,
        "BattleRunner",
        lambda **kwargs: SimpleNamespace(run=lambda **run_kwargs: result),
    )
    monkeypatch.setattr(api, "record_decision", lambda decision: None)
    monkeypatch.setattr(api, "record_battle", lambda payload: None)

    response = TestClient(api.app).post(
        "/gate/evaluate",
        json={"attack": "pod-kill", "version": "v9.9.9", "threshold": 70},
    )

    assert response.status_code == 200
    text = report_path.read_text(encoding="utf-8")
    assert "pod-kill" in text
    assert "v9.9.9" in text
    assert response.json()["report"]["text"] == text


def test_latest_report_uses_the_shared_report_file_constant(monkeypatch, tmp_path):
    report_path = tmp_path / "incident_report.md"
    report_path.write_text("# Current incident\n", encoding="utf-8")
    monkeypatch.setattr(api, "REPORT_FILE", report_path)

    client = TestClient(api.app)
    present = client.get("/report/latest")
    assert present.status_code == 200
    assert present.json() == {
        "file": str(report_path),
        "text": "# Current incident\n",
    }

    monkeypatch.setattr(api, "REPORT_FILE", tmp_path / "missing.md")
    absent = client.get("/report/latest")
    assert absent.status_code == 200
    assert absent.json() == {"file": str(tmp_path / "missing.md"), "text": None}


def test_cli_evaluation_also_refreshes_the_report(monkeypatch, tmp_path):
    from controller import cli as controller_cli
    from reporter.report import write_report as real_write_report

    result = _perfect()
    result.attack = "cpu-stress"
    report_path = tmp_path / "cli_incident_report.md"

    monkeypatch.setattr(
        controller_cli,
        "BattleRunner",
        lambda **kwargs: SimpleNamespace(run=lambda **run_kwargs: result),
    )
    monkeypatch.setattr(controller_cli, "record_decision", lambda decision: None)
    monkeypatch.setattr(controller_cli, "record_battle", lambda payload: None)
    monkeypatch.setattr(
        controller_cli,
        "write_report",
        lambda payload: real_write_report(payload, report_path),
    )

    code = controller_cli.main(
        ["evaluate", "--attack", "cpu-stress", "--version", "v9.9.9"]
    )

    assert code == 0
    text = report_path.read_text(encoding="utf-8")
    assert "cpu-stress" in text
    assert "v9.9.9" in text


def test_lab_status_is_distinct_from_api_health(monkeypatch):
    def fake_run_cli(module: str, *args: str, **kwargs: object) -> dict:
        if module == "attacker.cli":
            raise ControllerError("kubectl: no cluster")
        if module == "defender.cli":
            return {"ready": True, "url": "http://localhost:9090"}
        raise AssertionError(f"unexpected CLI call: {module} {args}")

    monkeypatch.setattr(api, "run_cli", fake_run_cli)
    client = TestClient(api.app)

    assert client.get("/health").json()["status"] == "ok"
    payload = client.get("/lab/status").json()
    assert payload["ready"] is False
    assert payload["kubernetes"] == {
        "ready": False,
        "detail": "kubectl: no cluster",
    }
    assert payload["prometheus"] == {
        "ready": True,
        "detail": "http://localhost:9090",
    }


def test_frontend_distinguishes_api_from_lab_readiness():
    api_js = (ROOT / "dashboard" / "src" / "api.js").read_text(encoding="utf-8")
    app = (ROOT / "dashboard" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "getLabStatus" in api_js
    assert "'/lab/status'" in api_js
    assert "labReady" in app
    assert "<span>Lab</span>" in app
    assert "API ONLINE · LAB NOT READY" in app
    assert "API connected · lab ready" in app
