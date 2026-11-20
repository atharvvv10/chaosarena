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
    for name in ["RESULTS.md", "TESTING.md", "BUILD_NOTES.md", "PORTFOLIO_POLISH.md", "DASHBOARD.md"]:
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


def test_evidence_endpoint_returns_committed_local_evidence():
    response = TestClient(api.app).get("/evidence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["last_battle"]["decision"]["verdict"] == "PROMOTE"
    assert payload["last_battle"]["battle"]["detected"] is True
    assert payload["last_battle"]["battle"]["detection_seconds"] > 0
    assert "attacker launch" in payload["last_battle"]["battle"]["detection_basis"]
    assert payload["last_battle"]["battle"]["recovery_seconds"] > 0
    assert payload["rl_benchmark"]["damage_ratio"] > 1
    assert "defender_forest_plus_deviation" in payload["defender_benchmark"]["detectors"]
    assert payload["no_defender_baseline"]["defender_remediation"] is False
    assert payload["bad_release_experiment"]["result"]["gate_caught_bad_release"] is True


def test_evidence_endpoint_tolerates_missing_and_invalid_files(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(api, "LAST_BATTLE_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api, "RL_BENCHMARK_FILE", bad)
    monkeypatch.setattr(api, "DEFENDER_BENCHMARK_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api, "NO_DEFENDER_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(api, "BAD_RELEASE_FILE", tmp_path / "missing.json")

    response = TestClient(api.app).get("/evidence")
    assert response.status_code == 200
    assert response.json() == {
        "last_battle": None,
        "rl_benchmark": None,
        "defender_benchmark": None,
        "no_defender_baseline": None,
        "bad_release_experiment": None,
    }


def test_no_defender_baseline_is_observe_only_and_recovered():
    payload = json.loads((ROOT / "ml" / "no_defender_baseline.json").read_text(encoding="utf-8"))
    assert payload["defender_remediation"] is False
    assert payload["detected"] is True
    assert payload["recovered"] is True
    assert payload["detection_seconds"] >= 0
    assert "attacker launch" in payload["detection_basis"]
    assert payload["recovery_seconds"] > 0
    assert payload["cleanup_ok"] is True
    assert payload["chaos_objects_remaining"] == 0

    script = (ROOT / "scripts" / "no_defender_baseline.py").read_text(encoding="utf-8")
    assert 'cli("defender.cli", "detect")' in script
    assert 'cli("attacker.cli", "cleanup")' in script
    assert "diagnose/act/run/verify action was taken" in script


def test_bad_release_experiment_blocks_then_promotes_after_rollback():
    payload = json.loads((ROOT / "ml" / "bad_release_experiment.json").read_text(encoding="utf-8"))
    bad = payload["bad_release"]["evidence"]
    rollback = payload["rollback"]["evidence"]
    assert bad["decision"]["verdict"] == "BLOCK"
    assert bad["score"]["score"] < 70
    assert bad["battle"]["recovered"] is False
    assert bad["battle"]["cleanup_ok"] is True
    assert rollback["decision"]["verdict"] == "PROMOTE"
    assert rollback["score"]["score"] >= 70
    assert rollback["battle"]["recovered"] is True
    assert rollback["battle"]["detection_seconds"] > 0
    assert payload["result"]["gate_caught_bad_release"] is True

    script = (ROOT / "scripts" / "bad_release_experiment.py").read_text(encoding="utf-8")
    assert "PAYMENT_FAILURE_RATE=1.0" in script
    assert "evaluate_gate" in script
    assert "set_failure_rate(original)" in script


def test_frontend_has_navigation_timeline_filters_and_report_actions():
    api_js = (DASHBOARD / "src" / "api.js").read_text(encoding="utf-8")
    app = (DASHBOARD / "src" / "App.jsx").read_text(encoding="utf-8")
    css = (DASHBOARD / "src" / "styles.css").read_text(encoding="utf-8")

    assert "/evidence" in api_js
    for label in [
        "Overview", "Battle", "Evidence", "History",
        "Battle timeline", "Learned vs random", "Detector comparison",
        "Recovery control", "Bad release vs rollback",
        "Search decision history", "Download", "Copy", "toast",
    ]:
        assert label in app, f"missing UI feature: {label}"
    for feature in ["subnav", "kpi-grid", "timeline", "benchmark-grid", "history-tools", ".toast"]:
        assert feature in css, f"missing style: {feature}"


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
