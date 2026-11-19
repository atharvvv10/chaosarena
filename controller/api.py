"""Small HTTP API for the release gate (used later by CI in Phase 6)."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .battle import BattleRunner
from .evidence import record_battle
from .gate import DEFAULT_THRESHOLD, evaluate_gate, last_decision, record_decision
from .score import score_battle

app = FastAPI(title="ChaosArena Gate", version="1.0.0")


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
