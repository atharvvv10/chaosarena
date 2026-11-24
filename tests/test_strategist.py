"""Tests for role-scoped LLM keys and the safe strategist/analyst wrappers."""
from __future__ import annotations

import json

import pytest

from attacker.strategist import ALLOWED_PAIRS, GroqStrategist, TemplateStrategist
from defender.analyst import GroqAnalyst, TemplateAnalyst
from reporter.cli import main as reporter_main
from reporter.llm import GroqLLM, LLMError
from reporter.role_clients import client_for, key_env, role_config


class FakeLLM:
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


def test_groq_strategist_falls_back_on_bad_proposal():
    strategist = GroqStrategist(client=FakeLLM("not json"), max_retries=1)
    proposal = strategist.propose({"score": 50})
    assert proposal.source == "template"
    assert strategist.last_error


def test_analyst_falls_back_on_bad_response():
    analyst = GroqAnalyst(client=FakeLLM("not json"), max_retries=1)
    result = analyst.analyse({"top_features": ["payment-service_p95_latency"]})
    assert result.source == "template"
    assert result.category == "latency"


def test_three_roles_use_three_distinct_keys(monkeypatch):
    monkeypatch.setenv("GROQ_ATTACKER_KEY", "key-attacker")
    monkeypatch.setenv("GROQ_DEFENDER_KEY", "key-defender")
    monkeypatch.setenv("GROQ_REPORT_KEY", "key-report")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    values = {
        role: client_for(role, backend="groq").api_key
        for role in ("attacker", "defender", "report")
    }
    assert values == {
        "attacker": "key-attacker",
        "defender": "key-defender",
        "report": "key-report",
    }
    assert [key_env(role) for role in ("attacker", "defender", "report")] == [
        "GROQ_ATTACKER_KEY",
        "GROQ_DEFENDER_KEY",
        "GROQ_REPORT_KEY",
    ]
    assert role_config("report")["key_set"] == "yes"


def test_shared_key_fallback_still_works(monkeypatch):
    monkeypatch.delenv("GROQ_ATTACKER_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "shared-key")
    assert client_for("attacker", backend="groq").api_key == "shared-key"


def test_missing_key_still_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_REPORT_KEY", raising=False)
    with pytest.raises(LLMError, match="GROQ_REPORT_KEY"):
        client_for("report", backend="groq")


def test_reporter_guard_mentions_role_key(capsys):
    assert reporter_main(["guard"]) == 0
    assert "GROQ_REPORT_KEY" in capsys.readouterr().out
