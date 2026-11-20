"""Small HTTP API for the release gate (used later by CI in Phase 6)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .battle import BattleRunner
from .evidence import record_battle
from .gate import (
    DEFAULT_THRESHOLD,
    evaluate_gate,
    last_decision,
    recent_decisions,
    record_decision,
)
from .score import score_battle

app = FastAPI(title="ChaosArena Gate", version="1.0.0")
RL_TABLE = Path("ml/rl_q_table.json")
LAST_BATTLE_FILE = Path("ml/last_battle.json")
RL_BENCHMARK_FILE = Path("ml/rl_benchmark.json")
DEFENDER_BENCHMARK_FILE = Path("ml/defender_benchmark.json")
NO_DEFENDER_FILE = Path("ml/no_defender_baseline.json")
BAD_RELEASE_FILE = Path("ml/bad_release_experiment.json")
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
    return payload


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
    path = Path("ml/incident_report.md")
    if not path.exists():
        return {"file": str(path), "text": None}
    return {"file": str(path), "text": path.read_text(encoding="utf-8")}


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
