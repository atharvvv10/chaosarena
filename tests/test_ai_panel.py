"""Tests for the v1.2 AI reasoning endpoint and dashboard panel."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from controller import api

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard" / "src"
KEY_PATTERN = r"gsk_[A-Za-z0-9]+|AQ\.Ab[A-Za-z0-9_.-]+"


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    monkeypatch.setattr(api, "AI_ADVISORIES_FILE", advisories)
    monkeypatch.setattr(api, "AI_ANALYSIS_FILE", analysis)
    monkeypatch.setattr(api, "DEEP_SUMMARY_FILE", summary)

    response = TestClient(api.app).get("/ai/reasoning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
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
