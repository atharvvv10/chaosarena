"""Phase 8: a small, local, free reinforcement-learning attacker.

The agent learns which allowlisted attack is most annoying to the Defender.
It never widens the Phase 2 allowlist, and its real mode only drives the
public controller CLI, never Kubernetes directly.
"""
from __future__ import annotations

from .agent import QLearningAgent
from .arena import ACTION_SPACE, REAL_ACTION_ALLOWLIST, Action, RealArena, SimArena

__all__ = [
    "Action",
    "ACTION_SPACE",
    "REAL_ACTION_ALLOWLIST",
    "QLearningAgent",
    "SimArena",
    "RealArena",
]
