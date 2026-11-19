"""Phase 4 Arena Controller: battle orchestration, resilience score and gate.

The controller only drives the public CLIs of the Phase 2 attacker and Phase 3
Defender. It never imports their internals, so it cannot bypass their allowlists.
"""
from .gate import DEFAULT_THRESHOLD, GateDecision, evaluate_gate, last_decision
from .score import BattleResult, ScoreResult, score_battle

__all__ = [
    "BattleResult",
    "ScoreResult",
    "GateDecision",
    "DEFAULT_THRESHOLD",
    "score_battle",
    "evaluate_gate",
    "last_decision",
]
