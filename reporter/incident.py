"""A flat, facts-only view of one battle for the incident reporter."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from controller.evidence import LAST_BATTLE


@dataclass
class Incident:
    version: str
    attack: str
    target: str
    detected: bool
    detection_seconds: float | None
    recovered: bool
    diagnosis: dict | None
    action_taken: dict | None
    score: int
    grade: str
    verdict: str
    reasons: list[str]
    deductions: list[str]
    cleanup_ok: bool
    chaos_objects_remaining: int
    evaluated_at: str

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "attack": self.attack,
            "target": self.target,
            "detected": self.detected,
            "detection_seconds": self.detection_seconds,
            "recovered": self.recovered,
            "diagnosis": self.diagnosis,
            "action_taken": self.action_taken,
            "score": self.score,
            "grade": self.grade,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "deductions": self.deductions,
            "cleanup_ok": self.cleanup_ok,
            "chaos_objects_remaining": self.chaos_objects_remaining,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_bundle(cls, payload: dict) -> "Incident":
        battle = payload["battle"]
        score = payload["score"]
        decision = payload["decision"]
        return cls(
            version=str(decision.get("version", battle.get("version", "candidate"))),
            attack=str(decision.get("attack", battle.get("attack", "unknown"))),
            target=str(decision.get("target", battle.get("target", "unknown"))),
            detected=bool(battle.get("detected")),
            detection_seconds=battle.get("detection_seconds"),
            recovered=bool(battle.get("recovered")),
            diagnosis=battle.get("diagnosis"),
            action_taken=battle.get("action_taken"),
            score=int(score.get("score", 0)),
            grade=str(score.get("grade", "F")),
            verdict=str(decision.get("verdict", "BLOCK")),
            reasons=[str(item) for item in decision.get("reasons", [])],
            deductions=[str(item) for item in score.get("deductions", [])],
            cleanup_ok=bool(battle.get("cleanup_ok")),
            chaos_objects_remaining=int(battle.get("chaos_objects_remaining", 0)),
            evaluated_at=str(decision.get("evaluated_at", "")),
        )


def load_latest(path: Path | str = LAST_BATTLE) -> Incident:
    """Load the most recent complete battle bundle."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(
            f"no battle evidence at {target}; run 'python -m controller.cli evaluate' first"
        )
    return Incident.from_bundle(json.loads(target.read_text(encoding="utf-8")))
