"""The release gate: promote only if the score and safety checks both pass."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .score import BattleResult, ScoreResult

DEFAULT_THRESHOLD = 70
DECISION_LOG = Path("ml/gate_decisions.jsonl")


@dataclass
class GateDecision:
    verdict: str
    promote: bool
    score: int
    threshold: int
    grade: str
    version: str
    attack: str
    target: str
    reasons: list[str] = field(default_factory=list)
    evaluated_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_gate(
    result: BattleResult,
    scored: ScoreResult,
    threshold: int = DEFAULT_THRESHOLD,
) -> GateDecision:
    """A score alone is not enough: cleanup safety is a hard requirement."""
    reasons: list[str] = []
    if scored.score >= threshold:
        reasons.append(f"score {scored.score} meets threshold {threshold}")
    else:
        reasons.append(f"score {scored.score} is below threshold {threshold}")

    if result.cleanup_ok:
        reasons.append("attack cleanup succeeded")
    else:
        reasons.append("attack cleanup failed")

    if result.chaos_objects_remaining == 0:
        reasons.append("no chaos objects left behind")
    else:
        reasons.append(f"{result.chaos_objects_remaining} chaos objects left behind")

    if result.attack_error:
        reasons.append(f"attacker error: {result.attack_error}")

    promote = (
        scored.score >= threshold
        and result.cleanup_ok
        and result.chaos_objects_remaining == 0
        and result.attack_error is None
    )

    return GateDecision(
        verdict="PROMOTE" if promote else "BLOCK",
        promote=promote,
        score=scored.score,
        threshold=threshold,
        grade=scored.grade,
        version=result.version,
        attack=result.attack,
        target=result.target,
        reasons=reasons,
        evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def record_decision(decision: GateDecision, path: Path | str = DECISION_LOG) -> Path:
    """Append one decision so every gate result can be audited later."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision.as_dict()) + "\n")
    return target


def last_decision(path: Path | str = DECISION_LOG) -> dict | None:
    target = Path(path)
    if not target.exists():
        return None
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None
