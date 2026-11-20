"""Turn one battle's evidence into a simple, explainable 0-100 score."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BattleResult:
    """Facts collected during one attack -> defend -> recover battle."""

    attack: str
    target: str
    version: str = "candidate"
    detected: bool = False
    detection_seconds: float | None = None
    detection_basis: str = "seconds since attacker launch until first anomaly observation"
    recovery_seconds: float | None = None
    recovered: bool = False
    final_score: float | None = None
    defender_threshold: float | None = None
    cleanup_ok: bool = False
    chaos_objects_remaining: int = 0
    diagnosis: dict | None = None
    action_taken: dict | None = None
    attack_error: str | None = None

    def as_dict(self) -> dict:
        return {
            "attack": self.attack,
            "target": self.target,
            "version": self.version,
            "detected": self.detected,
            "detection_seconds": self.detection_seconds,
            "detection_basis": self.detection_basis,
            "recovery_seconds": self.recovery_seconds,
            "recovered": self.recovered,
            "final_score": self.final_score,
            "defender_threshold": self.defender_threshold,
            "cleanup_ok": self.cleanup_ok,
            "chaos_objects_remaining": self.chaos_objects_remaining,
            "diagnosis": self.diagnosis,
            "action_taken": self.action_taken,
            "attack_error": self.attack_error,
        }


@dataclass
class ScoreResult:
    score: int
    deductions: list[str] = field(default_factory=list)
    grade: str = "A"

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "deductions": self.deductions,
        }


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def score_battle(result: BattleResult) -> ScoreResult:
    """Score from 100 downwards; every penalty names its reason.

    The rules are deliberately simple so a release decision can be explained
    in one sentence: did we see it, did it recover, and did we clean up?
    """
    penalties: list[tuple[int, str]] = []

    if not result.detected:
        penalties.append((30, "fault was never detected"))
    elif result.detection_seconds is not None and result.detection_seconds > 20:
        penalties.append((15, "detection took longer than 20 seconds"))

    if not result.recovered:
        penalties.append((25, "service did not return to a normal score"))

    if not result.cleanup_ok:
        penalties.append((20, "attack cleanup failed"))

    if result.chaos_objects_remaining > 0:
        penalties.append((20, "chaos objects were left behind"))

    if (
        result.final_score is not None
        and result.defender_threshold is not None
        and result.final_score > result.defender_threshold
    ):
        penalties.append((10, "final anomaly score is still above threshold"))

    if result.attack_error:
        penalties.append((10, "attacker reported an error"))

    total = sum(points for points, _ in penalties)
    score = max(0, 100 - total)
    deductions = [f"{reason} (-{points})" for points, reason in penalties]
    return ScoreResult(score=score, deductions=deductions, grade=_grade(score))
