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
    for name in ["RESULTS.md", "TESTING.md"]:
        assert (DOCS / name).exists()


def test_readme_marks_every_phase_complete():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Current status: Phase 9 complete" in readme
    for number in range(1, 10):
        assert f"Phase {number}" in readme
    assert "- [ ] Phase" not in readme


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
