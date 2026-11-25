"""Tests for the v1.2 AI reasoning endpoint and dashboard panel."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from controller import api
from controller.score import BattleResult
from reporter.llm import LLMError

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard" / "src"
KEY_PATTERN = r"gsk_[A-Za-z0-9_-]+|AIza[0-9A-Za-z_-]{20,}|AQ\.Ab[A-Za-z0-9_.-]+"
# Built from parts so a strict history scan never sees a key-shaped literal.
FAKE_GSK = "gsk_" + "fake" + "1234567890"
FAKE_AIZA = "AIza" + "12345678901234567890"
FAKE_AQ = "AQ.Ab." + "fake.key.12345678"
FAKE_SK = "sk-" + "fake" + "1234567890abcdef"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _battle_result() -> BattleResult:
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
        diagnosis={"category": "latency_spike", "service": "payment-service"},
        action_taken={"action": "restart", "service": "payment-service"},
    )


def test_ai_reasoning_endpoint_exposes_safe_role_evidence(tmp_path, monkeypatch):
    advisories = tmp_path / "advisories.json"
    analysis = tmp_path / "analysis.json"
    summary = tmp_path / "summary.json"
    _write(advisories, {
        "note": "Advisory only.",
        "calls": [
            {
                "role": "attacker_strategist", "ok": True, "latency_ms": 12.3,
                "result": {
                    "source": "groq", "attack": "pod-kill",
                    "target": "order-service", "duration": 30,
                    "rationale": "Top advisory idea.",
                },
            },
            {
                "role": "defender_analyst", "ok": True, "latency_ms": 45.6,
                "result": {"source": "gemini", "category": "traffic", "confidence": 0.8},
            },
            {
                "role": "dqn_attacker", "ok": True, "latency_ms": 1.2,
                "result": [{"action": "pod-kill@order-service", "q": 4.8}],
            },
        ],
    })
    _write(analysis, {
        "role": "defender_post_analysis", "ok": True, "latency_ms": 78.9,
        "result": {
            "source": "gemini", "category": "resilience_failure",
            "confidence": 1.0, "rationale": "Detected in 15.8 seconds.",
            "recommended_action": "Review recovery timing.",
        },
    })
    _write(summary, {
        "version": "v1.2-deep-aiml", "attack": "pod-kill", "target": "order-service",
        "verdict": "PROMOTE", "score": 100, "detected": True,
        "detection_seconds": 15.8, "recovery_seconds": 53.1,
        "report": {"backend": "groq", "chars": 1302, "saved_to": "ml/deep/live/incident_report.md"},
    })
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", tmp_path / "empty-runtime")
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", advisories)
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", analysis)
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", summary)

    response = TestClient(api.app).get("/ai/reasoning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["source"] == "saved-validation"
    assert payload["attacker"]["source"] == "groq"
    assert payload["attacker"]["attack"] == "pod-kill"
    assert payload["defender_preflight"]["source"] == "gemini"
    assert payload["dqn"]["result"][0]["action"] == "pod-kill@order-service"
    assert payload["defender_post"]["source"] == "gemini"
    assert payload["defender_post"]["category"] == "resilience_failure"
    assert payload["report"]["backend"] == "groq"
    assert payload["battle"]["verdict"] == "PROMOTE"
    assert "gsk_" not in json.dumps(payload)
    assert "AQ.Ab" not in json.dumps(payload)


def test_ai_reasoning_endpoint_handles_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", tmp_path / "empty-runtime")
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", tmp_path / "missing2.json")
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", tmp_path / "missing3.json")

    response = TestClient(api.app).get("/ai/reasoning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["attacker"] == {}
    assert payload["defender_post"] == {}
    assert payload["battle"]["verdict"] is None


def test_ai_reasoning_endpoint_prefers_fresh_runtime_notes(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    _write(runtime / "advisories.json", {
        "note": "Fresh advisory only.",
        "generated_at": "2026-11-25T10:00:00+00:00",
        "calls": [
            {
                "role": "attacker_strategist", "ok": True, "latency_ms": 11.0,
                "result": {"source": "groq", "attack": "pod-kill", "target": "order-service"},
            },
        ],
    })
    _write(runtime / "defender_analysis.json", {
        "role": "defender_post_analysis", "ok": True, "latency_ms": 22.0,
        "result": {"source": "gemini", "category": "fresh-finding"},
    })
    _write(runtime / "summary.json", {
        "version": "fresh-candidate", "attack": "pod-kill", "target": "order-service",
        "verdict": "BLOCK", "score": 65, "generated_at": "2026-11-25T10:00:00+00:00",
        "report": {"backend": "groq", "chars": 99},
    })
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", runtime)
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", tmp_path / "missing-advisories.json")
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", tmp_path / "missing-analysis.json")
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", tmp_path / "missing-summary.json")

    payload = TestClient(api.app).get("/ai/reasoning").json()

    assert payload["available"] is True
    assert payload["source"] == "fresh-battle"
    assert payload["generated_at"] == "2026-11-25T10:00:00+00:00"
    assert payload["attacker"]["attack"] == "pod-kill"
    assert payload["defender_post"]["category"] == "fresh-finding"


def test_evaluate_generates_fresh_ai_notes_when_enabled(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    result = _battle_result()
    monkeypatch.setattr(api, "REPORT_FILE", tmp_path / "incident_report.md")
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(
        api,
        "BattleRunner",
        lambda **kwargs: SimpleNamespace(run=lambda **run_kwargs: result),
    )
    monkeypatch.setattr(api, "record_decision", lambda decision: None)
    monkeypatch.setattr(api, "record_battle", lambda payload: None)
    calls: list[tuple[dict, Path]] = []

    def fake_notes(payload: dict, out: Path) -> dict:
        calls.append((payload, out))
        return {"available": True, "source": "fresh-battle"}

    monkeypatch.setattr(ai_notes, "generate_battle_ai_notes", fake_notes)

    response = TestClient(api.app).post(
        "/gate/evaluate",
        json={"attack": "network-latency", "version": "v9.9.9", "ai_enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["ai"]["source"] == "fresh-battle"
    assert len(calls) == 1
    assert calls[0][1] == tmp_path / "runtime"


def test_generate_battle_ai_notes_works_offline_without_keys(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    result = _battle_result()
    payload = {
        "battle": result.as_dict(),
        "score": {"score": 100, "grade": "A", "deductions": []},
        "decision": {
            "version": "v9.9.9", "attack": "network-latency",
            "target": "payment-service", "verdict": "PROMOTE", "score": 100,
            "reasons": [],
        },
    }

    def no_client(*args, **kwargs):  # noqa: ARG001 - simulates missing keys
        raise LLMError("no key configured")

    monkeypatch.setattr(ai_notes, "client_for", no_client)
    monkeypatch.setattr(
        ai_notes,
        "_dqn_rank",
        lambda: [{"action": "network-latency@payment-service", "q": 1.0}],
    )

    info = ai_notes.generate_battle_ai_notes(payload, tmp_path / "runtime")

    assert info["source"] == "fresh-battle"
    advisories = json.loads((tmp_path / "runtime" / "advisories.json").read_text(encoding="utf-8"))
    assert [call["role"] for call in advisories["calls"]] == [
        "attacker_strategist", "defender_analyst", "dqn_attacker"
    ]
    assert all(call["ok"] for call in advisories["calls"])
    assert advisories["calls"][0]["result"]["source"] == "template"
    assert advisories["calls"][1]["result"]["source"] == "template"
    summary_text = (tmp_path / "runtime" / "summary.json").read_text(encoding="utf-8")
    assert '"backend": "template"' in summary_text
    assert "gsk_" not in summary_text
    assert "AIza" not in summary_text


def test_generate_battle_ai_notes_survives_missing_torch(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    result = _battle_result()
    payload = {
        "battle": result.as_dict(),
        "score": {"score": 100, "grade": "A", "deductions": []},
        "decision": {"verdict": "PROMOTE", "score": 100, "reasons": []},
    }

    def no_client(*args, **kwargs):  # noqa: ARG001 - simulates missing keys
        raise LLMError("no key configured")

    def missing_dqn():
        raise ImportError("No module named 'torch'")

    monkeypatch.setattr(ai_notes, "client_for", no_client)
    monkeypatch.setattr(ai_notes, "_dqn_rank", missing_dqn)

    info = ai_notes.generate_battle_ai_notes(payload, tmp_path / "runtime")

    assert info["source"] == "fresh-battle"
    advisories = json.loads((tmp_path / "runtime" / "advisories.json").read_text(encoding="utf-8"))
    assert advisories["calls"][0]["ok"] is True
    assert advisories["calls"][1]["ok"] is True
    assert advisories["calls"][2]["ok"] is False
    assert "torch" in advisories["calls"][2]["last_error"]


def test_frontend_has_ai_reasoning_panel():
    api_js = (DASHBOARD / "api.js").read_text(encoding="utf-8")
    app = (DASHBOARD / "App.jsx").read_text(encoding="utf-8")
    css = (DASHBOARD / "styles.css").read_text(encoding="utf-8")

    assert "/ai/reasoning" in api_js
    for label in ["AI Reasoning", "Attack idea", "Defence reading", "Local + report"]:
        assert label in app
    for feature in ["ai-grid", "ai-panel", "ai-rationale"]:
        assert feature in app and feature in css
    assert "No API keys are displayed" in app
    assert "Refreshes while the page is open" in app
    assert "const SECTION_IDS=['overview','battle','evidence','aireasoning','history']" in app
    assert "SECTION_IDS[i]" in app
    assert "setInterval(()=>{if(!document.hidden)refresh(true)},15000)" in app
    assert "AI battle" in app
    assert 'id="aiEnabled"' in app
    assert "ai_enabled:aiEnabled" in app
    assert "Fresh AI notes loaded." in app
    assert "AI notes refresh failed." in app
    assert "const notesOk=updates[2].status==='fulfilled'&&updates[2].value?.available" in app
    assert "FRESH BATTLE NOTES" in app
    assert "Defender note" in app
    assert ".aiflag" in css


def test_committed_live_battle_evidence_is_green_and_key_free():
    import re

    summary_path = ROOT / "ml" / "deep" / "live" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["version"] == "v1.2-deep-aiml"
    assert summary["detected"] is True
    assert summary["detection_seconds"] > 0
    assert summary["recovery_seconds"] > 0
    assert summary["cleanup_ok"] is True
    assert summary["chaos_objects_remaining"] == 0
    assert summary["score"] >= 70
    assert summary["verdict"] == "PROMOTE"
    assert summary["report"]["backend"] == "groq"

    advisory_text = (ROOT / "ml" / "deep" / "live" / "advisories.json").read_text(encoding="utf-8")
    analysis_text = (ROOT / "ml" / "deep" / "live" / "defender_analysis.json").read_text(encoding="utf-8")
    report_text = (ROOT / "ml" / "deep" / "live" / "incident_report.md").read_text(encoding="utf-8")
    for text in (summary_path.read_text(encoding="utf-8"), advisory_text, analysis_text, report_text):
        assert not re.search(KEY_PATTERN, text)
    assert '"source": "groq"' in advisory_text
    assert '"source": "gemini"' in advisory_text
    assert '"source": "gemini"' in analysis_text


def test_live_battle_isolates_the_defender_action_log():
    actions = (ROOT / "defender" / "actions.py").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "live_deep_battle.py").read_text(encoding="utf-8")

    assert "CHAOSARENA_ACTION_LOG" in actions
    assert "CHAOSARENA_ACTION_LOG" in runner
    assert "ml/defender_actions.jsonl" not in runner
    assert "ml/deep/live/runtime/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_v12_media_is_fresh_and_v11_media_is_preserved():
    import hashlib

    shots = ROOT / "docs" / "screenshots"
    preserved_sha256 = {
        "dashboard.png": "C910C172E9C04679BD4D260BA3C0DAA24800B1ADA4F57960CD7444447E624377",
        "demo.gif": "B03FC56C7997C2F425FDC4E82236537E5A10005A435D4B5BD908C61A5A9DC289",
        "demo.mp4": "25C690653038814EF17D3A9C605130A528E2F4BBB78ED87D2B1155E393F0E73C",
        "grafana.png": "0A4705C102C950F4DF77BC14FAA4C7A2B37A432A6C6C05588D4DD222EB286502",
    }
    for name, expected in preserved_sha256.items():
        digest = hashlib.sha256((shots / name).read_bytes()).hexdigest().upper()
        assert digest == expected, f"v1.1 media changed: {name}"

    for name in ("v12_dashboard.png", "v12_ai_reasoning.png", "v12_demo.gif", "v12_demo.mp4"):
        path = shots / name
        assert path.exists(), f"missing {path}"
        assert path.stat().st_size > 10_000, f"asset looks empty: {path}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for token in ("v12_demo.gif", "v12_demo.mp4", "v12_dashboard.png", "v12_ai_reasoning.png"):
        assert token in readme

    capture = (ROOT / "scripts" / "capture_v12_media.py").read_text(encoding="utf-8")
    assert 'SHOTS / "v12_dashboard.png"' in capture
    assert 'SHOTS / "v12_ai_reasoning.png"' in capture
    assert 'SHOTS / "v12_demo.gif"' in capture
    assert 'SHOTS / "v12_demo.mp4"' in capture
    for old in ('SHOTS / "dashboard.png"', 'SHOTS / "demo.gif"', 'SHOTS / "demo.mp4"', 'SHOTS / "grafana.png"'):
        assert old not in capture
    assert "demo-media-v12" in (ROOT / "Makefile").read_text(encoding="utf-8")


def test_v12_ai_battle_media_shows_the_new_flow_without_overwriting_assets():
    shots = ROOT / "docs" / "screenshots"
    for name in (
        "v12_ai_battle_form.png",
        "v12_ai_battle_checkbox.png",
        "v12_ai_battle_reasoning.png",
        "v12_ai_battle_dashboard.png",
        "v12_ai_battle_demo.gif",
        "v12_ai_battle_demo.mp4",
    ):
        path = shots / name
        assert path.exists(), f"missing {path}"
        minimum = 1_000 if name == "v12_ai_battle_checkbox.png" else 10_000
        assert path.stat().st_size > minimum, f"asset looks empty: {path}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for token in (
        "v12_ai_battle_demo.gif", "v12_ai_battle_demo.mp4",
        "v12_ai_battle_form.png", "v12_ai_battle_checkbox.png",
        "v12_ai_battle_reasoning.png", "v12_ai_battle_dashboard.png",
    ):
        assert token in readme
    assert "![ChaosArena v1.2 AI battle walkthrough" in readme

    capture = (ROOT / "scripts" / "capture_ai_battle_media.py").read_text(encoding="utf-8")
    assert 'SHOTS / "v12_ai_battle_form.png"' in capture
    assert 'SHOTS / "v12_ai_battle_checkbox.png"' in capture
    assert 'SHOTS / "v12_ai_battle_reasoning.png"' in capture
    assert 'SHOTS / "v12_ai_battle_demo.gif"' in capture
    assert 'SHOTS / "v12_ai_battle_demo.mp4"' in capture
    for old in ('SHOTS / "dashboard.png"', 'SHOTS / "demo.gif"', 'SHOTS / "demo.mp4"', 'SHOTS / "grafana.png"'):
        assert old not in capture

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "demo-media-ai-battle" in makefile
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "docs/screenshots/_v12_ai_battle_frames/" in ignored
    assert "docs/screenshots/_v12_ai_battle_video/" in ignored


def _complete_saved_files(folder: Path) -> tuple[Path, Path, Path]:
    """Write a complete saved-validation set for fallback tests."""
    folder.mkdir(parents=True, exist_ok=True)
    advisories = folder / "advisories.json"
    analysis = folder / "defender_analysis.json"
    summary = folder / "summary.json"
    _write(advisories, {
        "note": "Saved advisory.",
        "calls": [{
            "role": "attacker_strategist", "ok": True, "latency_ms": 1.0,
            "result": {"source": "groq", "attack": "pod-kill", "target": "order-service"},
        }],
    })
    _write(analysis, {
        "role": "defender_post_analysis", "ok": True, "latency_ms": 2.0,
        "result": {"source": "gemini", "category": "saved-finding"},
    })
    _write(summary, {
        "version": "saved-candidate", "attack": "pod-kill", "target": "order-service",
        "verdict": "PROMOTE", "score": 100, "generated_at": "2026-11-20T00:00:00+00:00",
        "report": {"backend": "groq", "chars": 42},
    })
    return advisories, analysis, summary


def _monkeypatch_evaluator(tmp_path: Path, monkeypatch) -> None:
    """Keep gate tests local while still exercising the real API handler."""
    result = _battle_result()
    monkeypatch.setattr(api, "REPORT_FILE", tmp_path / "incident_report.md")
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(
        api,
        "BattleRunner",
        lambda **kwargs: SimpleNamespace(run=lambda **run_kwargs: result),
    )
    monkeypatch.setattr(api, "record_decision", lambda decision: None)
    monkeypatch.setattr(api, "record_battle", lambda payload: None)


def test_normal_battle_does_not_request_ai_notes(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    _monkeypatch_evaluator(tmp_path, monkeypatch)
    calls: list[tuple] = []

    def forbidden(*args, **kwargs):  # noqa: ARG001 - must never be called
        calls.append((args, kwargs))
        raise AssertionError("normal battle must not generate AI notes")

    monkeypatch.setattr(ai_notes, "generate_battle_ai_notes", forbidden)

    response = TestClient(api.app).post("/gate/evaluate", json={"version": "v9.9.9"})

    assert response.status_code == 200
    assert "ai" not in response.json()
    assert calls == []


def test_ai_failure_clears_stale_notes_and_redacts_error(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    _monkeypatch_evaluator(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("advisories.json", "defender_analysis.json", "summary.json"):
        _write(runtime / name, {"generated_at": "2026-11-25T09:00:00+00:00", "stale": True})
    saved = _complete_saved_files(tmp_path / "saved")
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", saved[0])
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", saved[1])
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", saved[2])

    def broken(*args, **kwargs):  # noqa: ARG001 - simulates a bad lazy import/call
        raise RuntimeError("authorization failed: " + FAKE_GSK)

    monkeypatch.setattr(ai_notes, "generate_battle_ai_notes", broken)

    client = TestClient(api.app)
    response = client.post("/gate/evaluate", json={"version": "v9.9.9", "ai_enabled": True})
    body = response.json()

    assert response.status_code == 200
    assert body["decision"]["verdict"] in {"PROMOTE", "BLOCK"}
    assert body["ai"]["available"] is False
    assert FAKE_GSK not in json.dumps(body)
    assert "[redacted]" in body["ai"]["error"]
    assert not (runtime / "summary.json").exists()

    notes = client.get("/ai/reasoning").json()
    assert notes["source"] == "saved-validation"
    assert FAKE_GSK not in json.dumps(notes)


def test_partial_runtime_notes_are_not_labelled_fresh(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    _write(runtime / "advisories.json", {
        "generated_at": "2026-11-25T10:00:00+00:00",
        "calls": [{"role": "attacker_strategist", "result": {"source": "groq"}}],
    })
    _write(runtime / "summary.json", {
        "generated_at": "2026-11-25T10:00:00+00:00", "verdict": "PROMOTE",
    })
    saved = _complete_saved_files(tmp_path / "saved")
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", runtime)
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", saved[0])
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", saved[1])
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", saved[2])

    payload = TestClient(api.app).get("/ai/reasoning").json()

    assert payload["source"] == "saved-validation"
    assert payload["battle"]["verdict"] == "PROMOTE"


def test_failed_dqn_last_error_is_exposed_by_endpoint(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    _write(runtime / "advisories.json", {
        "generated_at": "2026-11-25T11:00:00+00:00",
        "calls": [{
            "role": "dqn_attacker", "ok": False, "latency_ms": 3.0,
            "result": [], "last_error": "checkpoint missing",
        }],
    })
    _write(runtime / "defender_analysis.json", {
        "generated_at": "2026-11-25T11:00:00+00:00",
        "role": "defender_post_analysis",
        "result": {"source": "gemini", "category": "fresh-finding"},
    })
    _write(runtime / "summary.json", {
        "generated_at": "2026-11-25T11:00:00+00:00", "verdict": "PROMOTE",
    })
    monkeypatch.setattr(api, "AI_RUNTIME_DIR", runtime)
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", tmp_path / "missing-advisories.json")
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", tmp_path / "missing-analysis.json")
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", tmp_path / "missing-summary.json")

    payload = TestClient(api.app).get("/ai/reasoning").json()

    assert payload["source"] == "fresh-battle"
    assert payload["dqn"]["ok"] is False
    assert payload["dqn"]["last_error"] == "checkpoint missing"


def test_shared_redactor_covers_provider_key_shapes():
    from reporter.redaction import redact_text

    text = f"{FAKE_GSK} {FAKE_AIZA} {FAKE_AQ} {FAKE_SK}"

    redacted = redact_text(text)

    assert FAKE_GSK not in redacted
    assert FAKE_AIZA not in redacted
    assert FAKE_AQ not in redacted
    assert FAKE_SK not in redacted
    assert redacted.count("[redacted]") == 4


def test_fresh_notes_use_two_independent_defender_calls(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    seen: list[dict] = []

    class FakeDefenderClient:
        name = "gemini"

        def complete(self, prompt: str, facts: dict) -> str:  # noqa: ARG002
            facts_copy = dict(facts)
            seen.append(facts_copy)
            category = (
                "preflight-check"
                if facts_copy.get("stage") == "preflight-advisory"
                else "post-battle-check"
            )
            return json.dumps({
                "category": category,
                "confidence": 0.9,
                "rationale": "Advisory text.",
                "recommended_action": "Observe the allowlisted fault.",
            })

    monkeypatch.setattr(ai_notes, "client_for", lambda role, backend=None: FakeDefenderClient())
    monkeypatch.setattr(ai_notes, "_attack_call", lambda battle, ranked: {
        "role": "attacker_strategist", "ok": True, "latency_ms": 1.0,
        "result": {"source": "groq", "attack": "pod-kill", "target": "order-service"},
    })
    monkeypatch.setattr(ai_notes, "_dqn_rank", lambda: [])
    monkeypatch.setattr(ai_notes, "_report_call", lambda payload, out: {
        "backend": "template", "chars": 10, "saved_to": str(out / "incident_report.md"),
    })

    payload = {
        "battle": _battle_result().as_dict(),
        "score": {"score": 100, "grade": "A", "deductions": []},
        "decision": {"verdict": "PROMOTE", "score": 100, "reasons": []},
    }
    ai_notes.generate_battle_ai_notes(payload, tmp_path / "runtime")

    advisories = json.loads((tmp_path / "runtime" / "advisories.json").read_text(encoding="utf-8"))
    analysis = json.loads((tmp_path / "runtime" / "defender_analysis.json").read_text(encoding="utf-8"))
    roles = [call["role"] for call in advisories["calls"]]

    assert roles.count("defender_analyst") == 1
    assert analysis["role"] == "defender_post_analysis"
    assert analysis["generated_at"] == advisories["generated_at"]
    assert len(seen) == 2
    assert seen[0]["stage"] == "preflight-advisory"
    assert "detection_seconds" in seen[1]
    assert [call["result"]["category"] for call in advisories["calls"] if call["role"] == "defender_analyst"] == ["preflight-check"]
    assert analysis["result"]["category"] == "post-battle-check"


def test_report_fallback_reason_is_redacted(tmp_path, monkeypatch):
    import scripts.ai_notes as ai_notes

    def no_report_key(role, backend=None):  # noqa: ARG001 - only the report role fails
        if role == "report":
            raise LLMError("GROQ_REPORT_KEY " + FAKE_GSK + " is invalid")
        raise AssertionError("this test replaces the other roles")

    monkeypatch.setattr(ai_notes, "client_for", no_report_key)
    monkeypatch.setattr(ai_notes, "_attack_call", lambda battle, ranked: {
        "role": "attacker_strategist", "ok": True, "result": {"source": "template"},
    })
    monkeypatch.setattr(ai_notes, "_defence_call", lambda payload, stage="post": {
        "role": "defender_analyst" if stage == "preflight" else "defender_post_analysis",
        "ok": True, "result": {"source": "template"},
    })
    monkeypatch.setattr(ai_notes, "_dqn_rank", lambda: [])

    payload = {
        "battle": _battle_result().as_dict(),
        "score": {"score": 100, "grade": "A", "deductions": []},
        "decision": {"verdict": "PROMOTE", "score": 100, "reasons": []},
    }
    ai_notes.generate_battle_ai_notes(payload, tmp_path / "runtime")

    summary_text = (tmp_path / "runtime" / "summary.json").read_text(encoding="utf-8")
    assert '"backend": "template"' in summary_text
    assert "fallback_reason" in summary_text
    assert "[redacted]" in summary_text
    assert FAKE_GSK not in summary_text


def test_attacker_source_label_follows_backend_override():
    from attacker.strategist import GroqStrategist

    class FakeClient:
        name = "gemini"

    strategist = GroqStrategist(client=FakeClient())

    assert strategist.source == "gemini"


def test_advisory_modules_cannot_control_the_cluster_or_gate():
    for relative in (
        "scripts/ai_notes.py",
        "attacker/strategist.py",
        "defender/analyst.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for forbidden in ("kubectl", "ChaosMesh", "record_decision", "evaluate_gate", "subprocess.run"):
            assert forbidden not in text, f"{forbidden} found in {relative}"
