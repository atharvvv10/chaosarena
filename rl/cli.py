"""Command line: python -m rl.cli <command>."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from attacker.allowlist import ALLOWED_NAMESPACES
from attacker.specs import ATTACKS

from .agent import QLearningAgent
from .arena import (
    ACTION_SPACE,
    REAL_ACTION_ALLOWLIST,
    STATES,
    Action,
    ArenaError,
    RealArena,
    SimArena,
)

Q_TABLE = Path("ml/rl_q_table.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rl.cli",
        description="Phase 8 RL attacker: tabular Q-learning, sim + real.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guard", help="print the RL attacker's safety boundaries")

    train = sub.add_parser("train", help="learn in the free simulator (no cluster)")
    train.add_argument("--episodes", type=int, default=200)
    train.add_argument("--seed", type=int, default=7)
    train.add_argument("--output", default=str(Q_TABLE))

    policy = sub.add_parser("policy", help="show the learned policy from the Q table")
    policy.add_argument("--table", default=str(Q_TABLE))

    real = sub.add_parser("real", help="execute the best safe action in a real battle")
    real.add_argument("--episodes", type=int, default=1)
    real.add_argument("--duration", type=int, default=10)
    real.add_argument("--settle", type=int, default=20)
    real.add_argument("--threshold", type=int, default=0)
    real.add_argument("--epsilon", type=float, default=0.0)
    real.add_argument("--table", default=str(Q_TABLE))
    real.add_argument("--dry-run", action="store_true", help="print commands, run nothing")

    return parser


def train_agent(episodes: int, seed: int = 7, start: QLearningAgent | None = None) -> QLearningAgent:
    """Run Q-learning episodes against the deterministic simulator."""
    agent = start or QLearningAgent()
    arena = SimArena()
    rng = random.Random(seed)
    for _ in range(max(0, episodes)):
        state = "calm"
        for _step in range(2):
            action = agent.choose(state, rng=rng)
            result = arena.step(action)
            agent.update(state, action, result.reward, result.state)
            state = result.state
        agent.decay()
    return agent


def _load_or_train(table: str) -> QLearningAgent:
    path = Path(table)
    if path.exists():
        return QLearningAgent.load(path)
    return train_agent(episodes=200, seed=7)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command == "guard":
        print(json.dumps({
            "allowed_namespaces": sorted(ALLOWED_NAMESPACES),
            "action_space": [action.key for action in ACTION_SPACE],
            "real_action_allowlist": sorted(REAL_ACTION_ALLOWLIST),
            "attacks_available": sorted(ATTACKS),
            "simulation_needs_cluster": False,
            "real_interface": "controller.cli",
            "imports_kubernetes_directly": False,
            "paid_dependencies": [],
        }, indent=2))
        return 0

    if args.command == "train":
        if args.episodes < 1:
            parser.error("--episodes must be at least 1")
        agent = train_agent(args.episodes, seed=args.seed)
        path = agent.save(args.output)
        print(json.dumps({
            "episodes": args.episodes,
            "epsilon": agent.epsilon,
            "saved": str(path),
            "policy": {state: agent.ranked(state) for state in STATES},
        }, indent=2))
        return 0

    if args.command == "policy":
        table = getattr(args, "table", str(Q_TABLE))
        if not Path(table).exists():
            parser.error(f"Q table {table!r} not found; run `python -m rl.cli train`")
        agent = QLearningAgent.load(table)
        print(json.dumps({
            "table": table,
            "epsilon": agent.epsilon,
            "policy": {state: agent.ranked(state, limit=5) for state in STATES},
        }, indent=2))
        return 0

    if args.command == "real":
        if args.episodes < 1:
            parser.error("--episodes must be at least 1")
        agent = _load_or_train(args.table)
        agent.epsilon = args.epsilon
        arena = RealArena(
            duration=args.duration,
            settle=args.settle,
            threshold=args.threshold,
        )
        results = []
        for episode in range(args.episodes):
            state = "calm"
            action = agent.best_action(state, allowed=REAL_ACTION_ALLOWLIST)
            command = arena.command(action, version=f"rl-v{episode + 1}")
            if args.dry_run:
                results.append({"dry_run": True, "action": action.key, "command": command})
                continue
            try:
                result = arena.step(action, version=f"rl-v{episode + 1}")
            except ArenaError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            agent.update(state, action, result.reward, result.state)
            agent.decay()
            agent.save(args.table)
            results.append({
                "episode": episode + 1,
                "action": action.key,
                "score": result.score,
                "reward": result.reward,
                "verdict": result.detail["verdict"],
                "detected": result.detected,
                "next_state": result.state,
                "deductions": result.detail["deductions"],
            })
        print(json.dumps({
            "simulated": False,
            "table": args.table,
            "runs": results,
            "policy": {state: agent.ranked(state, limit=3) for state in STATES},
        }, indent=2))
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
