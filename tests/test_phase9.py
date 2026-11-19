"""Phase 9 acceptance tests: final docs, one-command verify and UI polish."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from controller import api

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DASHBOARD = ROOT / "dashboard"


def test_all_final_docs_exist():
    for number in range(1, 10):
        path = DOCS / f"phase{number}.md"
        assert path.exists(), f"missing {path}"
        assert len(path.read_text(encoding="utf-8")) > 200
    for name in ["RESULTS.md", "TESTING.md", "BUILD_NOTES.md", "PORTFOLIO_POLISH.md"]:
        assert (DOCS / name).exists()


def test_readme_leads_with_pitch_demo_and_honest_scope():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "resilience-gated ci/cd lab" in readme.lower()
    assert "docs/screenshots/demo.gif" in readme
    assert "docs/screenshots/demo.mp4" in readme
    assert "Results at a glance" in readme
    assert "Honest scope" in readme
    assert "not PPO" in readme
    assert "40 samples" in readme
    assert "BUILD_NOTES.md" in readme
    assert "Current status:" not in readme
    assert "## Verify Phase 1" not in readme
    assert "- [ ] Phase" not in readme
    for number in range(1, 10):
        assert f"Phase {number}" in readme


def test_verify_script_covers_every_cluster_free_check():
    script = (ROOT / "scripts" / "verify_all.py").read_text(encoding="utf-8")
    for fragment in [
        "pytest",
        "ci.gate",
        "controller.cli",
        "attacker.cli",
        "defender.cli",
        "rl.cli",
        "npm",
        "build",
    ]:
        assert fragment in script
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "verify:" in makefile
    assert "scripts/verify_all.py" in makefile


def test_rl_policy_endpoint_ranks_committed_q_values(tmp_path):
    table = tmp_path / "q.json"
    table.write_text(json.dumps({
        "epsilon": 0.05,
        "states": {
            "calm": {"pod-kill@order-service": 0.4, "network-partition@payment-service": 1.5},
            "alert": {"cpu-stress@order-service": 0.2},
        },
    }), encoding="utf-8")

    client = TestClient(api.app)
    original = api.RL_TABLE
    api.RL_TABLE = table
    try:
        response = client.get("/rl/policy")
    finally:
        api.RL_TABLE = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["epsilon"] == 0.05
    assert payload["states"]["calm"][0]["action"] == "network-partition@payment-service"
    assert payload["states"]["calm"][0]["q"] == 1.5
    assert len(payload["states"]["calm"]) == 2


def test_rl_policy_endpoint_handles_missing_table(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "RL_TABLE", tmp_path / "missing.json")
    response = TestClient(api.app).get("/rl/policy")
    assert response.status_code == 200
    assert response.json() == {"available": False, "states": {}}


def test_frontend_uses_polished_panels_and_rl_endpoint():
    api_js = (DASHBOARD / "src" / "api.js").read_text(encoding="utf-8")
    app = (DASHBOARD / "src" / "App.jsx").read_text(encoding="utf-8")
    css = (DASHBOARD / "src" / "styles.css").read_text(encoding="utf-8")

    assert "/rl/policy" in api_js
    for label in ["Release gate", "Run a battle", "RL attacker", "Decision history", "Incident report"]:
        assert label in app
    for feature in ["score-ring", "trend-bar", "phase-strip", "rl-panel"]:
        assert feature in app and feature in css
    assert "shop-test" in app


def test_main_entry_avoids_duplicate_dev_requests():
    main = (DASHBOARD / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "StrictMode" not in main
    assert "createRoot" in main
    assert "<App />" in main


def test_real_media_assets_exist_and_are_not_placeholders():
    shots = DOCS / "screenshots"
    for name in ["dashboard.png", "grafana.png", "demo.gif", "demo.mp4"]:
        path = shots / name
        assert path.exists(), f"missing {path}"
        assert path.stat().st_size > 10_000, f"asset looks empty: {path}"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Screenshots (placeholders)" not in readme


def test_docs_do_not_overclaim_gate_or_rl():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    results = (DOCS / "RESULTS.md").read_text(encoding="utf-8")
    phase4 = (DOCS / "phase4.md").read_text(encoding="utf-8")
    phase6 = (DOCS / "phase6.md").read_text(encoding="utf-8")
    text = "\n".join([readme, results, phase4, phase6]).lower()
    for overclaim in [
        "this proved the gate really can stop a release",
        "proves the gate can stop a bad release",
    ]:
        assert overclaim not in text
    assert "not ppo" in readme.lower()
    assert "measurement artefact" in results.lower() or "measurement timing" in readme.lower()
    assert "saved" in phase6.lower()


def test_benchmark_evidence_files_exist_and_are_committed():
    for name in ["rl_benchmark.json", "defender_benchmark.json"]:
        path = ROOT / "ml" / name
        assert path.exists(), f"missing {path}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload, f"empty benchmark evidence: {path}"
    rl = json.loads((ROOT / "ml" / "rl_benchmark.json").read_text(encoding="utf-8"))
    defender = json.loads((ROOT / "ml" / "defender_benchmark.json").read_text(encoding="utf-8"))
    assert rl["learned_does_more_damage"] is True
    assert "defender_forest_plus_deviation" in defender["detectors"]


def test_readme_reports_detection_timing_and_comparisons():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    results = (DOCS / "RESULTS.md").read_text(encoding="utf-8")
    combined = (readme + "\n" + results).lower()
    for label in ["detected in", "recovered in", "learned vs random", "detector comparison"]:
        assert label in combined, f"missing result section: {label}"
    assert "more damage than random" in combined.lower()
    assert "false" in combined.lower() and "positive" in combined.lower()


def test_final_project_has_no_secret_or_paid_ui_markers():
    sources = [
        *sorted((DASHBOARD / "src").glob("*")),
        ROOT / "scripts" / "verify_all.py",
        DOCS / "RESULTS.md",
        DOCS / "TESTING.md",
        DOCS / "phase9.md",
        ROOT / "README.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", text)
    for banned in ["stripe", "gsk_", "material-ui", "chart.js"]:
        assert banned not in text.lower()
