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

        def wait(self, timeout: float | None = None) -> int:
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


def test_observe_only_battle_polls_without_diagnosing_or_acting(monkeypatch, tmp_path):
    detections = iter(
        [
            {"score": 0.3, "threshold": 0.7, "anomaly": False},
            {"score": 0.9, "threshold": 0.7, "anomaly": True},
            {"score": 0.3, "threshold": 0.7, "anomaly": False},
        ]
    )
    run_calls: list[tuple[str, ...]] = []

    def fake_run_cli(module: str, *args: str, **kwargs: object) -> dict:
        if module == "attacker.cli" and args[0] == "status":
            return {"chaos_objects": []}
        if module == "defender.cli" and args[0] == "detect":
            return next(detections)
        if module == "defender.cli" and args[0] == "run":
            run_calls.append(args)
            raise AssertionError("observe-only trial must not run remediation")
        raise AssertionError(f"unexpected CLI call: {module} {args}")

    class FakeProcess:
        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls == 1 else 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        handle = kwargs["stdout"]
        handle.write(json.dumps({"ok": True, "cleanup_ok": True}) + "\n")
        return FakeProcess()

    monkeypatch.setattr(battle_module, "run_cli", fake_run_cli)
    monkeypatch.setattr(battle_module.subprocess, "Popen", fake_popen)

    runner = BattleRunner(
        poll_interval=0.01,
        settle_seconds=0,
        startup_settle_seconds=0,
        log_path=tmp_path / "observe_only.json",
    )
    result = runner.run(remediate=False)

    assert run_calls == []
    assert result.detected is True
    assert result.diagnosis is None
    assert result.action_taken is None
    assert result.recovered is True


def test_optional_post_detection_observation_records_anomaly_span(monkeypatch, tmp_path):
    normal = {"score": 0.3, "threshold": 0.7, "anomaly": False}
    detections = iter(
        [
            normal,
            {"score": 0.9, "threshold": 0.7, "anomaly": True},
            {"score": 0.9, "threshold": 0.7, "anomaly": True},
            normal,
        ]
    )
    hook_calls: list[float] = []

    def fake_run_cli(module: str, *args: str, **kwargs: object) -> dict:
        if module == "attacker.cli" and args[0] == "status":
            return {"chaos_objects": []}
        if module == "defender.cli" and args[0] == "detect":
            return next(detections, normal)
        if module == "defender.cli" and args[0] == "run":
            return {
                "diagnosis": {"category": "latency_spike"},
                "action_taken": {"action": "restart", "service": "order-service"},
            }
        raise AssertionError(f"unexpected CLI call: {module} {args}")

    class FakeProcess:
        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls <= 4 else 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        handle = kwargs["stdout"]
        handle.write(json.dumps({"ok": True, "cleanup_ok": True}) + "\n")
        return FakeProcess()

    def fake_hook(elapsed: float) -> dict:
        hook_calls.append(elapsed)
        return {"stressed_pod": "order-service-abc123"}

    monkeypatch.setattr(battle_module, "run_cli", fake_run_cli)
    monkeypatch.setattr(battle_module.subprocess, "Popen", fake_popen)

    runner = BattleRunner(
        poll_interval=0.05,
        settle_seconds=0,
        startup_settle_seconds=0,
        log_path=tmp_path / "observed.json",
    )
    result = runner.run(
        observe_after_detection=True,
        on_detection=fake_hook,
    )

    assert len(hook_calls) == 1
    assert result.detection_evidence == {"stressed_pod": "order-service-abc123"}
    assert result.anomaly_observations is not None
    assert len(result.anomaly_observations) == 4
    assert result.anomaly_active_seconds is not None
    assert result.anomaly_active_seconds > 0
    assert result.first_normal_after_detection_seconds is not None


def test_experimental_summary_reports_trials_and_holdout(tmp_path):
    from scripts import experimental_validation as validation

    trials_file = tmp_path / "trials.jsonl"
    trials_file.write_text(
        "\n".join(
            json.dumps(record)
            for record in [
                {
                    "trial": 1,
                    "configuration": "defender-enabled",
                    "status": "completed",
                    "detected": True,
                    "detection_seconds": 12.0,
                    "recovered": True,
                    "recovery_seconds": 60.0,
                    "defender_action_occurred": True,
                    "gate_verdict": "PROMOTE",
                    "final_score": 0.4,
                },
                {
                    "trial": 1,
                    "configuration": "observe-only",
                    "status": "completed",
                    "detected": True,
                    "detection_seconds": 14.0,
                    "recovered": True,
                    "recovery_seconds": 70.0,
                    "defender_action_occurred": False,
                    "gate_verdict": "PROMOTE",
                    "final_score": 0.5,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    holdout_file = tmp_path / "holdout.jsonl"
    holdout_file.write_text(
        "\n".join(
            json.dumps({"valid": True, "anomaly": anomaly, "score": score})
            for anomaly, score in [
                (False, 0.2),
                (False, 0.3),
                (False, 0.4),
                (True, 0.9),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = validation.write_summary(
        trials_file, holdout_file, tmp_path / "summary.json", None, None
    )

    assert payload["configurations"]["defender-enabled"]["detection_rate"] == 1.0
    assert payload["configurations"]["observe-only"]["recovery_seconds"]["median"] == 70
    assert payload["paired_recovery_delta_seconds"]["median"] == 10
    assert payload["holdout_normal"]["false_positives"] == 1
    assert payload["holdout_normal"]["false_positive_rate"] == 0.25
    sign = payload["paired_recovery_delta_seconds"]
    assert sign["sign_test_all_pairs"]["two_sided_p"] == 1.0
    assert sign["sign_test_acted_subgroup_post_hoc"]["n"] == 1


def test_exact_sign_test_matches_binomial_tail():
    from scripts import experimental_validation as validation

    assert validation._sign_test(8, 2)["two_sided_p"] == 0.109375
    assert validation._sign_test(8, 1)["two_sided_p"] == 0.039062
    assert validation._sign_test(5, 5)["two_sided_p"] == 1.0


def test_experimental_validation_report_has_required_sections_without_placeholders():
    report = (ROOT / "docs" / "EXPERIMENTAL_VALIDATION.md").read_text(
        encoding="utf-8"
    )
    for heading in [
        "Experimental questions and hypotheses",
        "Environment and methodology",
        "Trial-level results and summary statistics",
        "Defender-enabled versus observe-only comparison",
        "Detector evaluation results",
        "Unexpected findings and limitations",
        "Reproduction instructions",
    ]:
        assert heading in report
    assert "[RESULTS PENDING" not in report
    assert "HOLDOUT RESULTS PENDING" not in report


def test_frozen_evidence_snapshot_can_be_restored(monkeypatch, tmp_path):
    from scripts import experimental_validation as validation

    action_log = tmp_path / "defender_actions.jsonl"
    action_log.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(validation, "BACKUP_DIR", tmp_path / "frozen_backup")
    monkeypatch.setattr(validation, "MUTABLE_FROZEN_FILES", [action_log])

    validation.snapshot_frozen()
    action_log.write_text("original\nnew-action\n", encoding="utf-8")
    validation.restore_frozen()

    assert action_log.read_text(encoding="utf-8") == "original\n"
    assert not validation.BACKUP_DIR.exists()
