"""Tiny tabular Q-learning agent — standard library only, no paid ML service."""
from __future__ import annotations

import json
import random
from pathlib import Path

from .arena import ACTION_SPACE, STATES, Action


class QLearningAgent:
    """Epsilon-greedy tabular Q-learning over a fixed, allowlisted action space."""

    def __init__(
        self,
        actions: tuple[Action, ...] = ACTION_SPACE,
        alpha: float = 0.3,
        gamma: float = 0.8,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.97,
    ) -> None:
        self.actions = tuple(actions)
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.q: dict[str, dict[str, float]] = {
            state: {action.key: 0.0 for action in self.actions} for state in STATES
        }

    # ------------------------------------------------------------------ #
    # Policy
    # ------------------------------------------------------------------ #
    def choose(self, state: str, rng: random.Random | None = None) -> Action:
        """Pick an action: explore with probability epsilon, else exploit."""
        if state not in self.q:
            raise ValueError(f"unknown state {state!r}; expected one of {list(STATES)}")
        random_source = rng or random
        if random_source.random() < self.epsilon:
            return random_source.choice(self.actions)
        return self.best_action(state)

    def best_action(self, state: str, allowed: frozenset[str] | None = None) -> Action:
        """Highest-Q action; ties break in the fixed action-space order."""
        values = self.q[state]
        candidates = [action for action in self.actions if action.key in values]
        if allowed is not None:
            candidates = [action for action in candidates if action.key in allowed]
        if not candidates:
            raise ValueError(f"no allowed action for state {state!r}")
        return max(candidates, key=lambda action: values[action.key])

    def ranked(self, state: str, limit: int = 3) -> list[dict]:
        """Human-readable top actions for `policy` output."""
        values = self.q[state]
        ordered = sorted(self.actions, key=lambda action: values[action.key], reverse=True)
        return [
            {"action": action.key, "q": round(values[action.key], 4)}
            for action in ordered[:limit]
        ]

    # ------------------------------------------------------------------ #
    # Learning
    # ------------------------------------------------------------------ #
    def update(self, state: str, action: Action, reward: float, next_state: str) -> None:
        """Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]."""
        current = self.q[state][action.key]
        best_next = max(self.q[next_state].values())
        target = reward + self.gamma * best_next
        self.q[state][action.key] = round(current + self.alpha * (target - current), 6)

    def decay(self) -> None:
        """Lower epsilon after each episode so exploration fades over time."""
        self.epsilon = max(self.epsilon_min, round(self.epsilon * self.epsilon_decay, 6))

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "alpha": self.alpha,
            "gamma": self.gamma,
            "epsilon": self.epsilon,
            "states": self.q,
        }

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path | str) -> "QLearningAgent":
        target = Path(path)
        payload = json.loads(target.read_text(encoding="utf-8"))
        agent = cls(
            alpha=float(payload.get("alpha", 0.3)),
            gamma=float(payload.get("gamma", 0.8)),
            epsilon=float(payload.get("epsilon", 0.05)),
        )
        for state in STATES:
            saved = payload.get("states", {}).get(state, {})
            for action in agent.actions:
                if action.key in saved:
                    agent.q[state][action.key] = float(saved[action.key])
        return agent
