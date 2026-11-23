"""Phase 7 acceptance tests: free React UI + small gate API additions."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from controller import api
from controller.gate import recent_decisions

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def test_health_and_cors_for_vite_origin():
    client = TestClient(api.app)
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    preflight = client.options(
        "/gate/last",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_history_endpoint_uses_recent_decisions(monkeypatch):
    client = TestClient(api.app)
    fake = [{"verdict": "PROMOTE", "score": 100}, {"verdict": "BLOCK", "score": 40}]
    monkeypatch.setattr(api, "recent_decisions", lambda limit=10: fake[:limit])

    response = client.get("/gate/history?limit=1")
    assert response.status_code == 200
    assert response.json() == {"decisions": [fake[0]]}


def test_report_endpoint_returns_markdown(monkeypatch):
    class FakePath:
        def __init__(self, value):
            self.value = value

        def exists(self):
            return True

        def read_text(self, encoding=None):
            return "# Incident Report - test\n\n**Summary**\nok\n"

        def __str__(self):
            return self.value

    client = TestClient(api.app)
    monkeypatch.setattr(api, "REPORT_FILE", FakePath("ml/incident_report.md"))
    response = client.get("/report/latest")
    assert response.status_code == 200
    assert response.json()["file"] == "ml/incident_report.md"
    assert "**Summary**" in response.json()["text"]


def test_recent_decisions_helper_is_newest_first(tmp_path):
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"verdict": verdict, "score": score})
            for verdict, score in [("PROMOTE", 90), ("BLOCK", 50), ("PROMOTE", 100)]
        )
        + "\n",
        encoding="utf-8",
    )
    result = recent_decisions(limit=2, path=path)
    assert [item["score"] for item in result] == [100, 50]
    assert recent_decisions(limit=0, path=path) == []


def test_dashboard_uses_only_free_local_packages():
    package = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"] == {"react": "19.3.1", "react-dom": "19.3.1"}
    assert set(package["devDependencies"]) == {"@vitejs/plugin-react", "vite"}

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [DASHBOARD / "index.html", *sorted((DASHBOARD / "src").glob("*"))]
    )
    lowered = source.lower()
    for banned in ["material-ui", "antd", "chart.js", "stripe", "aws", "openai", "gsk_", "cdn."]:
        assert banned not in lowered

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in gitignore
    assert "dist/" in gitignore


def test_frontend_calls_all_gate_endpoints():
    api_js = (DASHBOARD / "src" / "api.js").read_text(encoding="utf-8")
    for endpoint in ["/health", "/gate/last", "/gate/history", "/report/latest", "/gate/evaluate", "/evidence"]:
        assert endpoint in api_js
    assert "VITE_API_URL" in api_js


def test_app_renders_all_main_panels():
    app_jsx = (DASHBOARD / "src" / "App.jsx").read_text(encoding="utf-8")
    for label in ["Release gate", "Run a battle", "Decision history", "Incident report"]:
        assert label in app_jsx
    assert "shop-test" in app_jsx
