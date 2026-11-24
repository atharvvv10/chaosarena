"""Deep Q-network attacker: a small PyTorch MLP with replay and a target net.

Deliberately CPU-only and seedable. It keeps the same public surface as the
tabular agent (``choose`` / ``best_action`` / ``ranked`` / ``decay``) so callers
can swap it in without learning a second API.
"""
from __future__ import annotations

import copy
import json
import random
from collections import deque
from pathlib import Path
from typing import Any, Sequence

import torch
from torch import nn
from torch.nn import functional as F

from .arena import ACTION_SPACE, Action
from .features import STATE_DIM

DEFAULT_MODEL = Path("ml/deep/dqn.pt")


class DQNAgent:
    """Epsilon-greedy DQN over the fixed seven-action allowlist."""

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        actions: tuple[Action, ...] = ACTION_SPACE,
        lr: float = 1e-3,
        gamma: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
        buffer_size: int = 10_000,
        batch_size: int = 32,
        target_sync: int = 50,
        seed: int = 42,
    ) -> None:
        self.actions = tuple(actions)
        self.state_dim = state_dim
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.target_sync = target_sync
        self.seed = seed
        self.rng = random.Random(seed)
        torch.manual_seed(seed)

        self.net = self._build(state_dim, len(self.actions))
        self.target = copy.deepcopy(self.net)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr)
        self.buffer: deque[tuple[list[float], int, float, list[float]]] = deque(
            maxlen=buffer_size
        )
        self.steps = 0
        self.losses: list[float] = []

    @staticmethod
    def _build(n_inputs: int, n_outputs: int) -> nn.Module:
        return nn.Sequential(
            nn.Linear(n_inputs, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, n_outputs),
        )

    # ------------------------------------------------------------------ #
    # Policy
    # ------------------------------------------------------------------ #
    def q_values(self, state: Sequence[float]) -> list[float]:
        self.net.eval()
        tensor = torch.as_tensor(state, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            return [round(float(v), 6) for v in self.net(tensor).squeeze(0)]

    def choose(self, state: Sequence[float], rng: random.Random | None = None) -> Action:
        random_source = rng or self.rng
        if random_source.random() < self.epsilon:
            return random_source.choice(self.actions)
        return self.best_action(state)

    def best_action(
        self, state: Sequence[float], allowed: frozenset[str] | None = None
    ) -> Action:
        values = self.q_values(state)
        candidates = list(enumerate(self.actions))
        if allowed is not None:
            candidates = [(i, a) for i, a in candidates if a.key in allowed]
        if not candidates:
            raise ValueError("no allowed action for the deep attacker")
        return max(candidates, key=lambda pair: values[pair[0]])[1]

    def ranked(self, state: Sequence[float], limit: int = 3) -> list[dict[str, Any]]:
        values = self.q_values(state)
        order = sorted(range(len(self.actions)), key=lambda i: values[i], reverse=True)
        return [
            {"action": self.actions[i].key, "q": values[i]} for i in order[:limit]
        ]

    # ------------------------------------------------------------------ #
    # Learning
    # ------------------------------------------------------------------ #
    def remember(
        self,
        state: Sequence[float],
        action: Action,
        reward: float,
        next_state: Sequence[float],
    ) -> None:
        self.buffer.append(
            (list(state), self.actions.index(action), float(reward), list(next_state))
        )

    def train_step(self) -> float | None:
        """One replay update. Returns the loss, or None while warming up."""
        if len(self.buffer) < self.batch_size:
            return None
        batch = self.rng.sample(list(self.buffer), self.batch_size)
        states = torch.as_tensor([row[0] for row in batch], dtype=torch.float32)
        actions = torch.tensor([row[1] for row in batch], dtype=torch.long)
        rewards = torch.tensor([row[2] for row in batch], dtype=torch.float32)
        next_states = torch.as_tensor([row[3] for row in batch], dtype=torch.float32)

        current = self.net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            future = self.target(next_states).max(dim=1).values
        desired = rewards + self.gamma * future

        loss = F.mse_loss(current, desired)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        value = round(float(loss.item()), 6)
        self.losses.append(value)
        self.steps += 1
        if self.steps % self.target_sync == 0:
            self.target.load_state_dict(self.net.state_dict())
        return value

    def decay(self) -> None:
        self.epsilon = max(self.epsilon_min, round(self.epsilon * self.epsilon_decay, 6))

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: Path | str = DEFAULT_MODEL) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.net.state_dict(),
                "config": {
                    "state_dim": self.state_dim,
                    "gamma": self.gamma,
                    "epsilon": self.epsilon,
                    "epsilon_min": self.epsilon_min,
                    "epsilon_decay": self.epsilon_decay,
                    "batch_size": self.batch_size,
                    "target_sync": self.target_sync,
                    "seed": self.seed,
                    "actions": [a.key for a in self.actions],
                },
                "steps": self.steps,
                "losses": self.losses[-500:],
            },
            target,
        )
        return target

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL) -> "DQNAgent":
        payload = torch.load(Path(path), map_location="cpu", weights_only=False)
        config = payload["config"]
        actions = tuple(
            next(a for a in ACTION_SPACE if a.key == key) for key in config.pop("actions")
        )
        agent = cls(actions=actions, **config)
        agent.net.load_state_dict(payload["state_dict"])
        agent.target.load_state_dict(payload["state_dict"])
        agent.steps = int(payload.get("steps", 0))
        agent.losses = list(payload.get("losses", []))
        return agent

    def describe(self) -> dict[str, Any]:
        return {
            "architecture": "MLP 10-64-64-7",
            "actions": [a.key for a in self.actions],
            "epsilon": self.epsilon,
            "replay_steps": self.steps,
            "last_loss": self.losses[-1] if self.losses else None,
            "seed": self.seed,
        }


def save_metrics(metrics: dict[str, Any], path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
