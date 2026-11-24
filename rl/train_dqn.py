"""Train the deep attacker entirely offline: python -m rl.train_dqn.

No cluster, no API key and no network. The checkpoint and metrics are written
under ``ml/deep/`` so the frozen v1.1 evidence is never touched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dqn_agent import DEFAULT_MODEL, DQNAgent, save_metrics
from .deep_arena import DeepSimArena
from .features import encode


def train(episodes: int = 120, steps: int = 12, seed: int = 42) -> tuple[DQNAgent, dict]:
    agent = DQNAgent(seed=seed)
    arena = DeepSimArena(seed=seed)
    episode_scores: list[float] = []
    all_losses: list[float] = []

    for episode in range(episodes):
        arena.reset(seed + episode)
        state = encode(None, None, 0, agent.epsilon, steps)
        total_reward = 0.0
        for step in range(steps):
            action = agent.choose(state)
            result = arena.step(action)
            next_state = encode(result, action, step, agent.epsilon, steps)
            agent.remember(state, action, result.reward, next_state)
            loss = agent.train_step()
            if loss is not None:
                all_losses.append(loss)
            total_reward += result.reward
            state = next_state
        episode_scores.append(round(total_reward / steps, 6))
        agent.decay()

    metrics = {
        "episodes": episodes,
        "steps_per_episode": steps,
        "seed": seed,
        "final_epsilon": agent.epsilon,
        "replay_steps": agent.steps,
        "mean_train_reward": round(sum(episode_scores) / len(episode_scores), 6) if episode_scores else 0.0,
        "mean_replay_loss": round(sum(all_losses) / len(all_losses), 6) if all_losses else None,
        "architecture": "MLP 10-64-64-7 with replay and target network",
        "simulator": "seeded DeepSimArena derived from recorded attack profiles",
    }
    return agent, metrics


def evaluate(agent: DQNAgent, episodes: int = 50, steps: int = 12, seed: int = 9000) -> dict:
    """Greedy evaluation on a fresh arena the agent has never seen."""
    arena = DeepSimArena(seed=seed)
    scores: list[float] = []
    rewards: list[float] = []
    chosen: list[str] = []
    for episode in range(episodes):
        arena.reset(seed + episode)
        state = encode(None, None, 0, 0.0, steps)
        total = 0.0
        for step in range(steps):
            action = agent.best_action(state)
            result = arena.step(action)
            chosen.append(action.key)
            total += result.reward
            state = encode(result, action, step, 0.0, steps)
        scores.append(result.score)
        rewards.append(round(total / steps, 6))
    counts: dict[str, int] = {}
    for key in chosen:
        counts[key] = counts.get(key, 0) + 1
    return {
        "episodes": episodes,
        "mean_score": round(sum(scores) / len(scores), 3),
        "mean_reward": round(sum(rewards) / len(rewards), 6),
        "action_counts": dict(sorted(counts.items())),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rl.train_dqn")
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(DEFAULT_MODEL))
    parser.add_argument("--metrics", default="ml/deep/dqn_training.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    agent, metrics = train(episodes=args.episodes, steps=args.steps, seed=args.seed)
    metrics["evaluation"] = evaluate(agent, seed=args.seed + 9000)
    path = agent.save(args.out)
    metrics_path = save_metrics(metrics, args.metrics)
    print(json.dumps({**metrics, "saved_to": str(path), "metrics_to": str(metrics_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
