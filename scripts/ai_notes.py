"""Generate fresh advisory notes for a dashboard AI-assisted battle.

The battle, allowlist and release gate are unchanged. This module only writes
safe, advisory text after a real battle has finished. Keys stay in the local
.gitignore'd .env file and are never returned to the browser.
"""
from __future__ import annotations

import json
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
from reporter.redaction import redact_text
from reporter.report import IncidentReporter
from reporter.role_clients import client_for, preferred_backend

_NOTE = "Advisory only; the CLI allowlist and classical detector own the real loop."

# Backwards-compatible alias used by the API and advisory tests.
_safe_error = redact_text


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


def _write_bundle(bundle: dict[Path, dict[str, Any]]) -> None:
    """Write all temporary files first, then publish the complete note set."""
    staged = []
    for path, payload in bundle.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staged.append((temporary, path))
    for temporary, path in staged:
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
        client = client_for("attacker", backend=preferred_backend("attacker"))
        strategist = GroqStrategist(
            client=client,
            fallback=_SelectedTemplateStrategist(ranked=ranked),
        )
        call = _timed("attacker_strategist", lambda: strategist.propose(observation).to_dict())
        if strategist.last_error:
            call["last_error"] = redact_text(strategist.last_error)
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


def _preflight_facts(battle: dict[str, Any]) -> dict[str, Any]:
    """Planned-fault facts only; no outcome leaks into the preflight advisory."""
    return {
        "attack": battle.get("attack"),
        "target": battle.get("target"),
        "duration": battle.get("duration"),
        "version": battle.get("version"),
        "stage": "preflight-advisory",
    }


def _defence_call(payload: dict[str, Any], stage: str = "post") -> dict[str, Any]:
    """Make one real role call; preflight and post-battle facts stay separate."""
    battle = payload.get("battle", {})
    if stage == "preflight":
        role = "defender_analyst"
        facts = _preflight_facts(battle)
    else:
        role = "defender_post_analysis"
        facts = _defence_facts(
            battle,
            payload.get("score", {}),
            payload.get("decision", {}),
        )
    try:
        analyst = LLMAnalyst(
            client=client_for("defender", backend=preferred_backend("defender")),
            fallback=TemplateAnalyst(),
        )
        call = _timed(role, lambda: analyst.analyse(facts).to_dict())
        if analyst.last_error:
            call["last_error"] = redact_text(analyst.last_error)
    except Exception as exc:  # noqa: BLE001 - no key means offline template
        call = _timed(role, lambda: TemplateAnalyst().analyse(facts).to_dict())
        call["last_error"] = redact_text(exc)
    return call


def _report_call(payload: dict[str, Any], out: Path) -> dict[str, Any]:
    incident = Incident.from_bundle(payload)
    target = out / "incident_report.md"
    fallback_reason = None
    try:
        report = IncidentReporter(
            client_for("report", backend=preferred_backend("report"))
        ).report(incident)
    except Exception as exc:  # noqa: BLE001 - deterministic section-valid fallback
        fallback_reason = redact_text(exc)
        report = IncidentReporter(TemplateLLM()).report(incident)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.text, encoding="utf-8")
    info = {
        "backend": report.backend,
        "chars": len(report.text),
        "saved_to": str(target),
    }
    if fallback_reason:
        info["fallback_reason"] = fallback_reason
    return info


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
    preflight_call = _defence_call(payload, stage="preflight")
    post_call = _defence_call(payload, stage="post")
    post_call["generated_at"] = generated_at

    report_info = _report_call(payload, out)
    advisories = {
        "note": _NOTE,
        "mode": "dashboard-ai-battle",
        "generated_at": generated_at,
        "calls": [attack_call, preflight_call, dqn_call],
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
    _write_bundle({
        out / "advisories.json": advisories,
        out / "defender_analysis.json": post_call,
        out / "summary.json": summary,
    })
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
