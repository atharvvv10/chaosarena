"""Learned vs random attacker comparison in the seeded simulator.

The per-attack effectiveness in `rl.arena.SIM_PROFILES` is a teaching prior taken
from the recorded Phase 3/4 battles, so this is an offline, reproducible
comparison — not a live cluster battle. It answers one question a recruiter
actually asks: does Q-learning find more damaging attacks than picking at random?

The attacker's reward is the damage it causes (lower resilience score is better
for the attacker), so a higher average reward means a more effective attacker.
"""
from __future__ import annotations

import random
from collections.abc import Callable

from .agent import QLearningAgent
from .arena import ACTION_SPACE, STATES, Action, SimArena

Policy = Callable[[str, random.Random], Action]


def _mean_reward_and_score(
    policy: Policy,
    arena: SimArena,
    episodes: int,
    rng: random.Random,
) -> tuple[float, float]:
    """Average reward and resilience score over two simulator steps per episode."""
    reward_total = 0.0
    score_total = 0.0
    steps = 0
    for _ in range(max(0, episodes)):
        state = STATES[0]
        for _step in range(2):
            action = policy(state, rng)
            result = arena.step(action)
            reward_total += result.reward
            score_total += result.score
            steps += 1
            state = result.state
    if steps == 0:
        return 0.0, 0.0
    return reward_total / steps, score_total / steps


def compare(agent: QLearningAgent, episodes: int = 200, seed: int = 7) -> dict:
    """Compare the greedy learned policy with a uniform random policy.

    `agent.epsilon` is ignored: the learned side always acts greedily from the
    saved Q-table, so the result measures what was learned rather than chance.
    """
    if episodes < 1:
        raise ValueError("episodes must be at least 1")
    arena = SimArena()

    def learned_policy(state: str, _rng: random.Random) -> Action:
        return agent.best_action(state)

    def random_policy(_state: str, rng: random.Random) -> Action:
        return rng.choice(ACTION_SPACE)

    learned_reward, learned_score = _mean_reward_and_score(
        learned_policy, arena, episodes, random.Random(seed)
    )
    random_reward, random_score = _mean_reward_and_score(
        random_policy, arena, episodes, random.Random(seed)
    )

    return {
        "simulated": True,
        "episodes": episodes,
        "seed": seed,
        "note": "offline seeded simulator; not a live cluster battle",
        "learned": {
            "avg_reward": round(learned_reward, 4),
            "avg_resilience_score": round(learned_score, 2),
            "best_action": agent.best_action(STATES[0]).key,
        },
        "random": {
            "avg_reward": round(random_reward, 4),
            "avg_resilience_score": round(random_score, 2),
        },
        "damage_ratio": round(learned_reward / random_reward, 2) if random_reward else None,
        "score_delta": round(learned_score - random_score, 2),
        "learned_does_more_damage": learned_reward > random_reward,
    }
