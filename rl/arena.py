"""Environments for the RL attacker: one simulated, one real.

Both environments expose the same tiny `step(action)` contract so the agent
code is identical. The simulator is seeded from the battles we already recorded;
the real environment runs the public `controller.cli` and reads its JSON.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from attacker.specs import ATTACKS

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Action:
    """One allowlisted attack + target pair."""

    attack: str
    target: str
    duration: int = 20

    @property
    def key(self) -> str:
        return f"{self.attack}@{self.target}"


# Every action is checked against the Phase 2 attack catalogue. Targets are the
# ones we actually exercised in earlier phases; there is no way for the learner
# to invent a new attack or a production target here.
ACTION_SPACE: tuple[Action, ...] = (
    Action("pod-kill", "order-service", 5),
    Action("pod-failure", "cart-service", 20),
    Action("network-latency", "payment-service", 20),
    Action("network-loss", "order-service", 20),
    Action("network-partition", "payment-service", 20),
    Action("cpu-stress", "order-service", 20),
    Action("memory-stress", "product-service", 20),
)
assert {action.attack for action in ACTION_SPACE} == set(ATTACKS)

# Real battles are slower and change committed evidence, so only attack/target
# pairs we have already proven safe may be executed in real mode. Simulation is
# free to explore the full action space.
REAL_ACTION_ALLOWLIST: frozenset[str] = frozenset(
    {
        "network-latency@payment-service",
        "pod-kill@order-service",
        "network-partition@payment-service",
    }
)

STATES: tuple[str, ...] = ("calm", "alert")


@dataclass(frozen=True)
class StepResult:
    """What an environment returns after one action."""

    state: str
    reward: float
    score: int
    detected: bool
    detail: dict


# Simulated effectiveness. These numbers are teaching priors taken from the
# recorded Phase 3/4 battles, not a claim about production behaviour. The
# attacker's reward is the damage it causes: a lower resilience score is better.
SIM_PROFILES: dict[str, dict[str, object]] = {
    "network-latency": {"score": 100, "detected": True},
    "pod-kill": {"score": 75, "detected": False},
    "network-partition": {"score": 70, "detected": False},
    "network-loss": {"score": 80, "detected": False},
    "cpu-stress": {"score": 85, "detected": False},
    "memory-stress": {"score": 85, "detected": False},
    "pod-failure": {"score": 90, "detected": False},
}


class ArenaError(RuntimeError):
    """Raised when an action cannot be executed safely."""


class SimArena:
    """Deterministic, cluster-free environment for fast learning."""

    def step(self, action: Action) -> StepResult:
        profile = SIM_PROFILES[action.attack]
        score = int(profile["score"])
        detected = bool(profile["detected"])
        return StepResult(
            state="calm" if detected else "alert",
            reward=round((100 - score) / 100, 4),
            score=score,
            detected=detected,
            detail={"simulated": True, "action": action.key},
        )


class RealArena:
    """Run one real battle through the public controller CLI."""

    def __init__(self, duration: int = 10, settle: int = 20, threshold: int = 0) -> None:
        self.duration = duration
        self.settle = settle
        self.threshold = threshold

    @staticmethod
    def validate(action: Action) -> None:
        if action.key not in REAL_ACTION_ALLOWLIST:
            raise ArenaError(
                f"real mode refuses unproven action {action.key!r}; "
                f"allowed: {sorted(REAL_ACTION_ALLOWLIST)}"
            )

    def command(self, action: Action, version: str = "rl-candidate") -> list[str]:
        """Build the exact public CLI command (also used by --dry-run)."""
        self.validate(action)
        return [
            sys.executable,
            "-m",
            "controller.cli",
            "evaluate",
            "--attack",
            action.attack,
            "--target",
            action.target,
            "--duration",
            str(self.duration),
            "--threshold",
            str(self.threshold),
            "--settle",
            str(self.settle),
            "--version",
            version,
        ]

    def step(self, action: Action, version: str = "rl-candidate") -> StepResult:
        command = self.command(action, version=version)
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        if not result.stdout.strip():
            raise ArenaError(
                f"controller.cli produced no JSON (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ArenaError(
                f"controller.cli produced invalid JSON: {result.stdout[:300]}"
            ) from exc

        battle = payload["battle"]
        score = int(payload["score"]["score"])
        detected = bool(battle["detected"])
        return StepResult(
            state="calm" if detected else "alert",
            reward=round((100 - score) / 100, 4),
            score=score,
            detected=detected,
            detail={
                "simulated": False,
                "action": action.key,
                "verdict": payload["decision"]["verdict"],
                "version": version,
                "deductions": payload["score"]["deductions"],
            },
        )
