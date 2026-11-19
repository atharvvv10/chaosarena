"""Phase 5 acceptance tests: facts-only prompt, validated report, offline default."""
from __future__ import annotations

import json

import pytest

from reporter import cli as reporter_cli
from reporter.incident import Incident, load_latest
from reporter.llm import GROQ_MODEL, GROQ_URL, GroqLLM, LLMError, OpenAICompatibleLLM, TemplateLLM, default_client
from reporter.prompt import build_prompt
from reporter.report import IncidentReporter, ReporterError, missing_sections
from reporter.sections import REQUIRED_SECTIONS


@pytest.fixture
def bundle() -> dict:
    return {
        "battle": {
            "attack": "network-latency",
            "target": "payment-service",
            "version": "v1.0.1",
            "detected": True,
            "detection_seconds": 13.9,
            "recovered": True,
            "final_score": 0.598,
            "defender_threshold": 0.7397,
            "cleanup_ok": True,
            "chaos_objects_remaining": 0,
            "diagnosis": {
                "category": "latency_spike",
                "service": "order-service",
                "confidence": 0.99,
                "evidence": ["order-service_p95_latency z=+272.5"],
            },
            "action_taken": {
                "action": "restart",
                "service": "order-service",
                "namespace": "shop-test",
                "timestamp": "2026-11-19T12:25:54+00:00",
            },
            "attack_error": None,
        },
        "score": {"score": 100, "grade": "A", "deductions": []},
        "decision": {
            "verdict": "PROMOTE",
            "score": 100,
            "threshold": 70,
            "grade": "A",
            "version": "v1.0.1",
            "attack": "network-latency",
            "target": "payment-service",
            "reasons": ["score 100 meets threshold 70", "attack cleanup succeeded"],
            "evaluated_at": "2026-11-19T12:26:21+00:00",
        },
    }


def _write(tmp_path, bundle: dict):
    path = tmp_path / "last_battle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #
def test_incident_from_bundle_keeps_only_facts(bundle):
    incident = Incident.from_bundle(bundle)
    assert incident.version == "v1.0.1"
    assert incident.attack == "network-latency"
    assert incident.detected is True
    assert incident.detection_seconds == 13.9
    assert incident.diagnosis["service"] == "order-service"
    assert incident.verdict == "PROMOTE"
    assert "recovered" in incident.as_dict()


def test_load_latest_reads_saved_bundle(tmp_path, bundle):
    incident = load_latest(_write(tmp_path, bundle))
    assert incident.score == 100
    assert incident.cleanup_ok is True


def test_load_latest_gives_clear_error_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="evaluate"):
        load_latest(tmp_path / "missing.json")


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def test_prompt_contains_facts_and_required_sections(bundle):
    prompt = build_prompt(Incident.from_bundle(bundle))
    assert "order-service" in prompt
    assert "13.9" in prompt
    assert "PROMOTE" in prompt
    for section in REQUIRED_SECTIONS:
        assert section in prompt
    assert "Do not invent" in prompt


# --------------------------------------------------------------------------- #
# Offline template report
# --------------------------------------------------------------------------- #
def test_template_report_has_all_sections_and_real_numbers(bundle):
    incident = Incident.from_bundle(bundle)
    report = IncidentReporter(TemplateLLM()).report(incident)
    assert missing_sections(report.text) == []
    assert "# Incident Report - v1.0.1" in report.text
    assert "**100/100 (grade A)**" in report.text
    assert "**PROMOTE**" in report.text
    assert "13.9 seconds" in report.text
    assert "latency_spike" in report.text
    assert report.backend == "template"


def test_report_validation_rejects_incomplete_text(bundle):
    class BadClient:
        name = "bad"
        def complete(self, prompt, facts):
            return "# Incident Report\n\n## Summary\nSomething happened."

    with pytest.raises(ReporterError, match="missing required sections"):
        IncidentReporter(BadClient()).report(Incident.from_bundle(bundle))


def test_missing_sections_lists_each_one():
    missing = missing_sections("## Summary\n\n## Timeline\n")
    assert "Root cause" in missing
    assert "Follow-ups" in missing
    assert missing_sections("# A\n## Summary\n## Timeline\n## Root cause\n## Actions taken\n## Outcome\n## Follow-ups") == []


def test_missing_sections_accepts_bold_headings_from_real_llms():
    text = "\n".join(f"**{section}**" for section in REQUIRED_SECTIONS)
    assert missing_sections(text) == []


def test_default_backend_is_offline(monkeypatch):
    monkeypatch.delenv("CHAOSARENA_LLM_BACKEND", raising=False)
    assert isinstance(default_client(), TemplateLLM)


def test_openai_backend_requires_url(monkeypatch):
    monkeypatch.delenv("CHAOSARENA_LLM_URL", raising=False)
    with pytest.raises(LLMError, match="CHAOSARENA_LLM_URL"):
        OpenAICompatibleLLM(api_key="unused")


def test_openai_backend_parses_a_chat_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "# Report\n## Summary\nok"}}]
            }).encode("utf-8")

    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleLLM(url="http://localhost:11434/v1/chat/completions", api_key="secret")
    text = client.complete("prompt", {})
    assert text == "# Report\n## Summary\nok"
    assert seen["url"].endswith("/chat/completions")
    assert seen["timeout"] == 120


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_guard_is_offline_by_default(capsys):
    code = reporter_cli.main(["guard"])
    assert code == 0
    output = capsys.readouterr().out
    assert '"network_used_by_default": false' in output
    assert "Summary" in output


def test_cli_report_writes_markdown_file(tmp_path, bundle, capsys):
    evidence = _write(tmp_path, bundle)
    out = tmp_path / "report.md"
    code = reporter_cli.main([
        "--evidence", str(evidence), "report", "--backend", "template", "--out", str(out)
    ])
    assert code == 0
    saved = out.read_text(encoding="utf-8")
    assert "## Root cause" in saved
    assert "v1.0.1" in saved
    assert '"backend": "template"' in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Free Groq tier
# --------------------------------------------------------------------------- #
def test_groq_backend_uses_free_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "free-key")
    client = GroqLLM()
    assert client.url == GROQ_URL
    assert client.model == GROQ_MODEL
    assert client.api_key == "free-key"
    assert client.name == "groq"


def test_groq_backend_requires_a_free_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        GroqLLM()


def test_default_client_can_select_groq(monkeypatch):
    monkeypatch.setenv("CHAOSARENA_LLM_BACKEND", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "free-key")
    assert isinstance(default_client(), GroqLLM)
