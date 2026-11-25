"""Generate fresh advisory notes for a dashboard AI-assisted battle.

The battle, allowlist and release gate are unchanged. This module only writes
safe, advisory text after a real battle has finished. Keys stay in the local
.gitignore'd .env file and are never returned to the browser.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from attacker.strategist import (
    ALLOWED_PAIRS,
    GroqStrategist,
    StrategyProposal,
    TemplateStrategist,
)
from defender.analyst import LLMAnalyst, TemplateAnalyst
from reporter.incident import Incident
from reporter.llm import TemplateLLM
from reporter.report import IncidentReporter
from reporter.role_clients import client_for, preferred_backend

_KEY_PATTERN = re.compile(r"gsk_[A-Za-z0-9_-]+|AIza[0-9A-Za-z_-]{20,}")
_NOTE = "Advisory only; the CLI allowlist and classical detector own the real loop."


def _safe_error(exc: Exception) -> str:
    """Truncate provider errors and redact anything resembling a key."""
    text = " ".join(str(exc).split())[:300]
    return _KEY_PATTERN.sub("[redacted]", text)


def _timed(role: str, call: Callable[[], Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
        return {
            "role": role,
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001 - advisory failures never fail the gate
        return {
            "role": role,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "result": {},
            "last_error": _safe_error(exc),
        }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _duration(value: Any) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return 30
    return max(1, min(duration, 300))


class _SelectedTemplateStrategist(TemplateStrategist):
    """Offline fallback that keeps the user's already-allowlisted selection."""

    def propose(self, observation: dict[str, Any]) -> StrategyProposal:
        attack = str(observation.get("attack") or "")
        target = str(observation.get("target") or "")
        if (attack, target) in ALLOWED_PAIRS:
            return StrategyProposal(
                attack=attack,
                target=target,
                duration=_duration(observation.get("duration")),
                rationale="Offline advisory for the selected allowlisted pair.",
                source="template",
            )
        return super().propose(observation)


def _dqn_rank() -> list[dict[str, Any]]:
    """Load the local DQN only when available; torch is not a CI dependency."""
    from rl.dqn_agent import DEFAULT_MODEL, DQNAgent
    from rl.features import encode

    agent = DQNAgent.load(DEFAULT_MODEL)
    agent.epsilon = 0.0
    return agent.ranked(encode(None, None, 0, 0.0))


def _dqn_call() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    try:
        ranked = _dqn_rank()
        call = {
            "role": "dqn_attacker",
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "result": ranked,
        }
    except Exception as exc:  # noqa: BLE001 - local checkpoint is optional
        ranked = []
        call = {
            "role": "dqn_attacker",
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "result": [],
            "last_error": _safe_error(exc),
        }
    return ranked, call


def _attack_call(battle: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
    observation = {
        "attack": battle.get("attack"),
        "target": battle.get("target"),
        "duration": battle.get("duration"),
        "version": battle.get("version"),
        "stage": "post-battle-advisory",
    }
    try:
        strategist = GroqStrategist(
            client=client_for("attacker", backend=preferred_backend("attacker")),
            fallback=_SelectedTemplateStrategist(ranked=ranked),
        )
        call = _timed("attacker_strategist", lambda: strategist.propose(observation).to_dict())
        if strategist.last_error:
            call["last_error"] = strategist.last_error
    except Exception as exc:  # noqa: BLE001 - no key means offline template
        call = _timed(
            "attacker_strategist",
            lambda: _SelectedTemplateStrategist(ranked=ranked).propose(observation).to_dict(),
        )
        call["last_error"] = _safe_error(exc)
    return call


def _defence_facts(battle: dict[str, Any], score: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "attack": battle.get("attack"),
        "target": battle.get("target"),
        "version": battle.get("version"),
        "detected": battle.get("detected"),
        "detection_seconds": battle.get("detection_seconds"),
        "recovery_seconds": battle.get("recovery_seconds"),
        "cleanup_ok": battle.get("cleanup_ok"),
        "final_score": battle.get("final_score"),
        "threshold": battle.get("defender_threshold"),
        "score": score.get("score"),
        "verdict": decision.get("verdict"),
    }


def _defence_call(payload: dict[str, Any]) -> dict[str, Any]:
    facts = _defence_facts(
        payload.get("battle", {}),
        payload.get("score", {}),
        payload.get("decision", {}),
    )
    try:
        analyst = LLMAnalyst(
            client=client_for("defender", backend=preferred_backend("defender")),
            fallback=TemplateAnalyst(),
        )
        call = _timed("defender_analyst", lambda: analyst.analyse(facts).to_dict())
        if analyst.last_error:
            call["last_error"] = analyst.last_error
    except Exception as exc:  # noqa: BLE001 - no key means offline template
        call = _timed("defender_analyst", lambda: TemplateAnalyst().analyse(facts).to_dict())
        call["last_error"] = _safe_error(exc)
    return call


def _report_call(payload: dict[str, Any], out: Path) -> dict[str, Any]:
    incident = Incident.from_bundle(payload)
    target = out / "incident_report.md"
    try:
        report = IncidentReporter(
            client_for("report", backend=preferred_backend("report"))
        ).report(incident)
    except Exception:  # noqa: BLE001 - deterministic section-valid fallback
        report = IncidentReporter(TemplateLLM()).report(incident)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.text, encoding="utf-8")
    return {
        "backend": report.backend,
        "chars": len(report.text),
        "saved_to": str(target),
    }


def generate_battle_ai_notes(payload: dict[str, Any], out: Path) -> dict[str, Any]:
    """Write fresh advisory evidence for one already-completed battle."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    battle = payload.get("battle", {})
    score = payload.get("score", {})
    decision = payload.get("decision", {})
    ranked, dqn_call = _dqn_call()
    attack_call = _attack_call(battle, ranked)
    defence_call = _defence_call(payload)
    post_call = dict(defence_call)
    post_call["role"] = "defender_post_analysis"
    if isinstance(post_call.get("result"), dict):
        post_call["result"] = dict(post_call["result"])

    report_info = _report_call(payload, out)
    advisories = {
        "note": _NOTE,
        "mode": "dashboard-ai-battle",
        "generated_at": generated_at,
        "calls": [attack_call, defence_call, dqn_call],
    }
    summary = {
        "version": decision.get("version") or battle.get("version") or "candidate",
        "attack": battle.get("attack") or decision.get("attack"),
        "target": battle.get("target") or decision.get("target"),
        "verdict": decision.get("verdict"),
        "score": decision.get("score"),
        "detected": battle.get("detected"),
        "detection_seconds": battle.get("detection_seconds"),
        "recovery_seconds": battle.get("recovery_seconds"),
        "cleanup_ok": battle.get("cleanup_ok"),
        "chaos_objects_remaining": battle.get("chaos_objects_remaining"),
        "generated_at": generated_at,
        "mode": "dashboard-ai-battle",
        "report": report_info,
        "advisories": advisories,
    }
    _write_json(out / "advisories.json", advisories)
    _write_json(out / "defender_analysis.json", post_call)
    _write_json(out / "summary.json", summary)
    return {
        "available": True,
        "source": "fresh-battle",
        "generated_at": generated_at,
        "note": _NOTE,
        "files": {
            "advisories": str(out / "advisories.json"),
            "analysis": str(out / "defender_analysis.json"),
            "summary": str(out / "summary.json"),
        },
    }
