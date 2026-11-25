"""Small HTTP API for the release gate (used later by CI in Phase 6)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .battle import BattleRunner, ControllerError, run_cli
from .evidence import record_battle
from .gate import (
    DEFAULT_THRESHOLD,
    evaluate_gate,
    last_decision,
    recent_decisions,
    record_decision,
)
from .score import score_battle
from reporter.redaction import redact_text
from reporter.report import write_report

app = FastAPI(title="ChaosArena Gate", version="1.0.0")
RL_TABLE = Path("ml/rl_q_table.json")
LAST_BATTLE_FILE = Path("ml/last_battle.json")
REPORT_FILE = Path("ml/incident_report.md")
RL_BENCHMARK_FILE = Path("ml/rl_benchmark.json")
DEFENDER_BENCHMARK_FILE = Path("ml/defender_benchmark.json")
NO_DEFENDER_FILE = Path("ml/no_defender_baseline.json")
BAD_RELEASE_FILE = Path("ml/bad_release_experiment.json")
DEEP_LIVE_DIR = Path("ml/deep/live")
AI_RUNTIME_DIR = DEEP_LIVE_DIR / "runtime"
AI_ADVISORIES_FILE = DEEP_LIVE_DIR / "advisories.json"
AI_ANALYSIS_FILE = DEEP_LIVE_DIR / "defender_analysis.json"
DEEP_SUMMARY_FILE = DEEP_LIVE_DIR / "summary.json"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class EvaluateRequest(BaseModel):
    attack: str = "network-latency"
    target: str = "payment-service"
    duration: int = Field(default=30, ge=1, le=300)
    threshold: int = Field(default=DEFAULT_THRESHOLD, ge=0, le=100)
    version: str = "candidate"
    settle: int = Field(default=45, ge=0, le=180)
    ai_enabled: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "chaosarena-gate"}


def _read_evidence(path: Path) -> dict | None:
    """Return committed local evidence, or None when a file is absent/invalid."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _refresh_report(payload: dict) -> dict:
    """Regenerate the incident report from the battle that was just evaluated."""
    report = write_report(payload, REPORT_FILE)
    return {"file": str(REPORT_FILE), "backend": report.backend, "text": report.text}


def _clear_runtime_notes() -> None:
    """Drop fresh notes when a later AI battle fails before writing them."""
    for name in (
        "advisories.json", "defender_analysis.json", "summary.json",
        "incident_report.md", "generation_error.json",
    ):
        try:
            (AI_RUNTIME_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass


def _lab_probe(module: str) -> dict:
    """Probe lab readiness only through the published CLI boundary."""
    try:
        payload = run_cli(module, "ready", timeout=10)
    except ControllerError as exc:
        return {"ready": False, "detail": str(exc)}
    detail = payload.get("detail") or payload.get("namespace") or payload.get("url") or "reachable"
    return {"ready": bool(payload.get("ready")), "detail": str(detail)}


@app.get("/lab/status")
def lab_status() -> dict:
    """Report API-independent Kubernetes and Prometheus readiness."""
    kubernetes = _lab_probe("attacker.cli")
    prometheus = _lab_probe("defender.cli")
    return {
        "ready": kubernetes["ready"] and prometheus["ready"],
        "kubernetes": kubernetes,
        "prometheus": prometheus,
    }


@app.get("/evidence")
def evidence() -> dict:
    """Bundled local evidence used by the dashboard's battle and benchmark panels."""
    return {
        "last_battle": _read_evidence(LAST_BATTLE_FILE),
        "rl_benchmark": _read_evidence(RL_BENCHMARK_FILE),
        "defender_benchmark": _read_evidence(DEFENDER_BENCHMARK_FILE),
        "no_defender_baseline": _read_evidence(NO_DEFENDER_FILE),
        "bad_release_experiment": _read_evidence(BAD_RELEASE_FILE),
    }


def _view_llm_call(call: dict | None) -> dict:
    """Expose only safe advisory fields; never echo client config or keys."""
    if not isinstance(call, dict) or not call:
        return {}
    result = call.get("result")
    view = {
        "role": call.get("role"),
        "ok": bool(call.get("ok")),
        "latency_ms": call.get("latency_ms"),
    }
    if call.get("last_error"):
        view["last_error"] = redact_text(call["last_error"])
    if not isinstance(result, dict):
        view["result"] = result
        return view
    view["source"] = result.get("source")
    for key in (
        "attack", "target", "duration", "rationale", "category",
        "confidence", "recommended_action", "cached", "allowed",
    ):
        if key in result:
            view[key] = result[key]
    return view


def _ai_files() -> tuple[dict, dict, dict, str]:
    """Prefer notes written by the newest AI-assisted dashboard battle."""
    runtime = (
        AI_RUNTIME_DIR / "advisories.json",
        AI_RUNTIME_DIR / "defender_analysis.json",
        AI_RUNTIME_DIR / "summary.json",
    )
    committed = (AI_ADVISORIES_FILE, AI_ANALYSIS_FILE, DEEP_SUMMARY_FILE)
    runtime_payloads = tuple(_read_evidence(path) for path in runtime)
    if all(isinstance(item, dict) and item for item in runtime_payloads):
        stamps = {
            item.get("generated_at")
            for item in runtime_payloads
            if item.get("generated_at")
        }
        if len(stamps) <= 1:
            return (*runtime_payloads, "fresh-battle")
    committed_payloads = tuple(_read_evidence(path) for path in committed)
    if all(isinstance(item, dict) and item for item in committed_payloads):
        return (*committed_payloads, "saved-validation")
    return {}, {}, {}, "saved-validation"


@app.get("/ai/reasoning")
def ai_reasoning() -> dict:
    """Read the newest safe AI advisory evidence for the dashboard."""
    advisories, analysis, summary, source = _ai_files()
    calls = advisories.get("calls")
    by_role = {
        call.get("role"): call
        for call in calls
        if isinstance(call, dict) and call.get("role")
    } if isinstance(calls, list) else {}

    report = summary.get("report")
    report = report if isinstance(report, dict) else {}
    battle = {
        "version": summary.get("version"),
        "attack": summary.get("attack"),
        "target": summary.get("target"),
        "verdict": summary.get("verdict"),
        "score": summary.get("score"),
        "detected": summary.get("detected"),
        "detection_seconds": summary.get("detection_seconds"),
        "recovery_seconds": summary.get("recovery_seconds"),
    }
    return {
        "available": bool(advisories or analysis or summary),
        "source": source,
        "generated_at": summary.get("generated_at"),
        "note": advisories.get("note") or (
            "Advisory only; the CLI allowlist and classical detector own the real loop."
        ),
        "battle": battle,
        "attacker": _view_llm_call(by_role.get("attacker_strategist")),
        "defender_preflight": _view_llm_call(by_role.get("defender_analyst")),
        "dqn": _view_llm_call(by_role.get("dqn_attacker")),
        "defender_post": _view_llm_call(analysis),
        "report": {
            "backend": report.get("backend"),
            "chars": report.get("chars"),
            "saved_to": report.get("saved_to"),
            "fallback_reason": report.get("fallback_reason"),
        },
    }


@app.post("/gate/evaluate")
def evaluate(request: EvaluateRequest) -> dict:
    """Run a real battle and return the promotion decision."""
    result = BattleRunner(settle_seconds=request.settle).run(
        attack=request.attack,
        target=request.target,
        duration=request.duration,
        version=request.version,
    )
    scored = score_battle(result)
    decision = evaluate_gate(result, scored, threshold=request.threshold)
    record_decision(decision)
    payload = {
        "battle": result.as_dict(),
        "score": scored.as_dict(),
        "decision": decision.as_dict(),
    }
    record_battle(payload)
    response = dict(payload)
    response["report"] = _refresh_report(payload)
    if request.ai_enabled:
        try:
            from scripts.ai_notes import generate_battle_ai_notes

            response["ai"] = generate_battle_ai_notes(payload, AI_RUNTIME_DIR)
        except Exception as exc:  # noqa: BLE001 - AI is advisory, the gate stands
            _clear_runtime_notes()
            response["ai"] = {
                "available": False,
                "source": "fresh-battle-error",
                "error": redact_text(exc),
            }
    return response


@app.get("/gate/last")
def last() -> dict:
    decision = last_decision()
    return {"decision": decision} if decision else {"decision": None}


@app.get("/gate/history")
def history(limit: int = 10) -> dict:
    """Newest-first decisions for the dashboard timeline."""
    return {"decisions": recent_decisions(limit=limit)}


@app.get("/report/latest")
def latest_report() -> dict:
    """Return the offline incident report for the dashboard panel."""
    if not REPORT_FILE.exists():
        return {"file": str(REPORT_FILE), "text": None}
    return {"file": str(REPORT_FILE), "text": REPORT_FILE.read_text(encoding="utf-8")}


@app.get("/rl/policy")
def rl_policy() -> dict:
    """Read the committed Q table; never imports the RL or attacker modules."""
    if not RL_TABLE.exists():
        return {"available": False, "states": {}}
    payload = json.loads(RL_TABLE.read_text(encoding="utf-8"))
    states: dict[str, list[dict]] = {}
    for state, values in payload.get("states", {}).items():
        ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)[:3]
        states[state] = [
            {"action": action, "q": round(float(score), 4)} for action, score in ranked
        ]
    return {
        "available": True,
        "epsilon": payload.get("epsilon"),
        "states": states,
    }
