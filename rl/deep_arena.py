"""Seeded, noisy simulator used to train the deep attacker.

``SimArena`` in :mod:`rl.arena` is intentionally deterministic because it backs
the frozen v1.1 evidence. This arena is new: it adds small seeded variation so
a neural policy has something to learn from, while keeping every attack inside
the same seven-action allowlist.
"""
from __future__ import annotations

import random

from .arena import Action, StepResult, SIM_PROFILES


class DeepSimArena:
    """A stochastic teaching arena built from the recorded attack profiles."""

    def __init__(self, seed: int = 42, noise: float = 0.06) -> None:
        self.seed = seed
        self.noise = noise
        self.rng = random.Random(seed)
        self.calls = 0
        self.last_attack: str | None = None

    def reset(self, seed: int | None = None) -> None:
        """Restart the RNG so two policies can see identical attack sequences."""
        self.rng = random.Random(self.seed if seed is None else seed)
        self.calls = 0
        self.last_attack = None

    def step(self, action: Action) -> StepResult:
        profile = SIM_PROFILES[action.attack]
        base_score = float(profile["score"])
        score = max(
            0.0,
            min(100.0, base_score + self.rng.gauss(0.0, self.noise * 100.0)),
        )
        # Even a normally-detectable fault has a small chance of slipping past a
        # noisy detector, and a quiet one can trigger a false alarm. That is what
        # makes the policy learn detection risk rather than just raw damage.
        # The defender adapts: repeating the same attack family makes detection
        # more likely. The vector-state DQN can see the previous action; the
        # two-state tabular agent cannot, which is the point of the comparison.
        detect_chance = 0.90 if profile["detected"] else 0.12
        if action.attack == self.last_attack:
            detect_chance = min(1.0, detect_chance + 0.35)
        detected = self.rng.random() < detect_chance
        anomaly = max(0.0, min(1.0, score / 100.0 + self.rng.gauss(0.0, 0.02)))
        reward = round((100.0 - score) / 100.0 - (0.05 if detected else 0.0), 6)
        self.last_attack = action.attack
        self.calls += 1
        return StepResult(
            state="calm" if detected else "alert",
            reward=reward,
            score=round(score, 2),
            detected=detected,
            detail={
                "simulated": True,
                "deep": True,
                "action": action.key,
                "anomaly_score": round(anomaly, 6),
            },
        )
