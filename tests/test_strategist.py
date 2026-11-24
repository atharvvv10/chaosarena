"""Tests for provider-scoped LLM keys and safe strategist/analyst wrappers."""
from __future__ import annotations

import json

import pytest

from attacker.strategist import ALLOWED_PAIRS, GroqStrategist, TemplateStrategist
from defender.analyst import LLMAnalyst, TemplateAnalyst
from reporter.cli import main as reporter_main
from reporter.llm import GEMINI_MODEL, GeminiLLM, GroqLLM, LLMError
from reporter.role_clients import (
    client_for,
    gemini_key_env,
    groq_key_env,
    key_env,
    preferred_backend,
    role_config,
)


class FakeLLM:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, prompt, facts):
        self.calls += 1
        return self.text


def test_template_strategist_only_proposes_allowlisted_pairs():
    proposal = TemplateStrategist().propose({"score": 60})
    assert (proposal.attack, proposal.target) in ALLOWED_PAIRS
    assert proposal.to_dict()["allowed"] is True


def test_groq_strategist_parses_and_caches(monkeypatch):
    monkeypatch.setenv("GROQ_ATTACKER_KEY", "attacker-key")
    fake = FakeLLM(json.dumps({
        "attack": "pod-kill",
        "target": "order-service",
        "duration": 7,
        "rationale": "quiet fault",
    }))
    strategist = GroqStrategist(client=fake)
    first = strategist.propose({"score": 50})
    second = strategist.propose({"score": 50})
    assert first.source == "groq"
    assert first.duration == 7
    assert second.cached is True
    assert fake.calls == 1


def test_groq_strategist_accepts_duration_strings():
    fake = FakeLLM(json.dumps({
        "attack": "pod-kill",
        "target": "order-service",
        "duration": "60s",
        "rationale": "valid but human-formatted duration",
    }))
    proposal = GroqStrategist(client=fake, max_retries=1).propose({"score": 50})
    assert proposal.source == "groq"
    assert proposal.duration == 60


def test_groq_strategist_falls_back_on_bad_proposal():
    strategist = GroqStrategist(client=FakeLLM("not json"), max_retries=1)
    proposal = strategist.propose({"score": 50})
    assert proposal.source == "template"
    assert strategist.last_error


def test_analyst_falls_back_on_bad_response():
    analyst = LLMAnalyst(client=FakeLLM("not json"), max_retries=1)
    result = analyst.analyse({"top_features": ["payment-service_p95_latency"]})
    assert result.source == "template"
    assert result.category == "latency"


def test_three_roles_use_two_groq_keys_and_one_gemini_key(monkeypatch):
    monkeypatch.setenv("GROQ_ATTACKER_KEY", "key-attacker")
    monkeypatch.setenv("GEMINI_DEFENDER_KEY", "key-defender")
    monkeypatch.setenv("GROQ_REPORT_KEY", "key-report")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    values = {
        role: client_for(role, backend=preferred_backend(role)).api_key
        for role in ("attacker", "defender", "report")
    }
    assert values == {
        "attacker": "key-attacker",
        "defender": "key-defender",
        "report": "key-report",
    }
    assert [key_env(role) for role in ("attacker", "defender", "report")] == [
        "GROQ_ATTACKER_KEY",
        "GEMINI_DEFENDER_KEY",
        "GROQ_REPORT_KEY",
    ]
    assert [preferred_backend(role) for role in ("attacker", "defender", "report")] == [
        "groq", "gemini", "groq",
    ]
    assert role_config("defender")["key_set"] == "yes"
    assert role_config("defender")["gemini_key_set"] == "yes"


def test_shared_key_fallback_still_works(monkeypatch):
    monkeypatch.delenv("GROQ_ATTACKER_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "shared-groq")
    assert client_for("attacker", backend="groq").api_key == "shared-groq"


def test_gemini_shared_key_fallback_still_works(monkeypatch):
    monkeypatch.delenv("GEMINI_DEFENDER_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini")
    assert client_for("defender", backend="gemini").api_key == "shared-gemini"


def test_missing_role_keys_still_raise(monkeypatch):
    for name in (
        "GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_ATTACKER_KEY",
        "GEMINI_DEFENDER_KEY", "GROQ_REPORT_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMError, match="GROQ_ATTACKER_KEY"):
        client_for("attacker", backend="groq")
    with pytest.raises(LLMError, match="GEMINI_DEFENDER_KEY"):
        client_for("defender", backend="gemini")
    with pytest.raises(LLMError, match="GROQ_REPORT_KEY"):
        client_for("report", backend="groq")


def test_gemini_backend_uses_role_key_and_parses_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({
                "candidates": [{
                    "content": {"parts": [{"text": "root-cause-note"}]}
                }]
            }).encode("utf-8")

    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("GEMINI_DEFENDER_KEY", "defender-gemini")
    client = client_for("defender", backend="gemini")
    assert isinstance(client, GeminiLLM)
    assert client.api_key == "defender-gemini"
    assert client.url.endswith(f"{GEMINI_MODEL}:generateContent")
    assert client.complete("prompt", {}) == "root-cause-note"
    assert seen["timeout"] == 120


def test_key_env_rejects_unknown_provider():
    with pytest.raises(LLMError, match="unknown provider"):
        key_env("attacker", "anthropic")


def test_reporter_guard_mentions_both_provider_keys(capsys):
    assert reporter_main(["guard"]) == 0
    output = capsys.readouterr().out
    assert "GROQ_REPORT_KEY" in output
    assert "GEMINI_DEFENDER_KEY" in output


def test_provider_key_helpers_are_explicit():
    assert groq_key_env("attacker") == "GROQ_ATTACKER_KEY"
    assert gemini_key_env("defender") == "GEMINI_DEFENDER_KEY"
