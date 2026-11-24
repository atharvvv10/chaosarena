"""Offline validation of the v1.2 AIML upgrade.

Compares the DQN attacker with the tabular Q-learning attacker and scores the
LSTM defender, shipped Defender, 3-sigma rule and Isolation Forest on the same
seeded holdout. Writes only to ``ml/deep/`` so the frozen v1.1 evidence is never
modified. No cluster and no API key are needed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from defender.benchmark import RULE_Z
from defender.collect import load_baseline
from defender.model import Detector, baseline_stats
from defender.neural import NeuralDetector
from rl.agent import QLearningAgent
from rl.arena import ACTION_SPACE
from rl.dqn_agent import DQNAgent
from rl.deep_arena import DeepSimArena
from rl.features import encode


def compare_attackers(
    episodes: int = 30, steps: int = 12, seed: int = 9000
) -> dict[str, Any]:
    """Greedy evaluation of both policies on identical seeded arena sessions."""
    deep_agent = DQNAgent.load("ml/deep/dqn.pt")
    deep_agent.epsilon = 0.0
    tabular = QLearningAgent()
    tabular.epsilon = 0.0
    arena = DeepSimArena(seed=seed)

    deep_rewards: list[float] = []
    tabular_rewards: list[float] = []
    deep_scores: list[float] = []
    tabular_scores: list[float] = []

    for episode in range(episodes):
        arena.reset(seed + episode)
        state = encode(None, None, 0, 0.0, steps)
        deep_total = 0.0
        for step in range(steps):
            action = deep_agent.best_action(state)
            result = arena.step(action)
            deep_total += result.reward
            state = encode(result, action, step, 0.0, steps)
        deep_rewards.append(round(deep_total / steps, 6))
        deep_scores.append(float(result.score))

        arena.reset(seed + episode)
        state = "calm"
        tabular_total = 0.0
        for step in range(steps):
            action = tabular.best_action(state)
            result = arena.step(action)
            tabular_total += result.reward
            state = result.state
        tabular_rewards.append(round(tabular_total / steps, 6))
        tabular_scores.append(float(result.score))

    wins = sum(d > t for d, t in zip(deep_rewards, tabular_rewards))
    losses = sum(d < t for d, t in zip(deep_rewards, tabular_rewards))
    return {
        "episodes": episodes,
        "seed": seed,
        "deep": {
            "mean_reward": round(float(np.mean(deep_rewards)), 6),
            "mean_final_score": round(float(np.mean(deep_scores)), 3),
        },
        "tabular": {
            "mean_reward": round(float(np.mean(tabular_rewards)), 6),
            "mean_final_score": round(float(np.mean(tabular_scores)), 3),
        },
        "seeded_simulator_wins": {
            "deep_better": wins,
            "tabular_better": losses,
            "episodes": episodes,
        },
        "note": (
            "Both policies see the same seeded RNG stream per episode, but choose "
            "different actions, so the pairing is approximate rather than exact. "
            "This is a seeded simulator outcome, not an independent statistical "
            "trial: the simulator reward makes repeated attacks easier to detect, "
            "which the vector-state DQN can exploit while the tabular state cannot."
        ),
    }


def compare_defenders(
    samples: int = 30, seed: int = 4242, epochs: int = 250
) -> dict[str, Any]:
    """False alarms on noisy normal traffic and detection of seeded spikes."""
    rows = load_baseline("ml/baseline.csv")
    split = max(5, len(rows) // 4)
    train_rows, calibration_rows = rows[:-split], rows[-split:]
    classical = Detector.train(train_rows)
    mean, std = baseline_stats(train_rows)
    neural = NeuralDetector(seed=seed)
    neural.train(train_rows, epochs=epochs)
    neural.calibrate(calibration_rows, quantile=0.99, margin=0.1)
    rng = np.random.default_rng(seed)
    matrix = np.asarray(rows, dtype=np.float32)
    scale = np.where(matrix.std(axis=0) < 1e-9, 1.0, matrix.std(axis=0))
    window = neural.window

    normal_scores: list[float] = []
    anomaly_scores: list[float] = []
    classical_normal: list[float] = []
    classical_anomaly: list[float] = []
    forest_normal: list[float] = []
    forest_anomaly: list[float] = []
    rule_normal: list[float] = []
    rule_anomaly: list[float] = []

    def forest_only_score(vector: Sequence[float]) -> float:
        row = np.asarray(vector, dtype=float).reshape(1, -1)
        return float(-classical.forest.score_samples(row)[0])

    def rule_score(vector: Sequence[float]) -> float:
        z = np.abs((np.asarray(vector, dtype=float) - mean) / std)
        return float(np.max(z))

    for anomalous in (False, True):
        for _ in range(samples):
            base = matrix[rng.integers(0, len(matrix))].copy()
            if anomalous:
                index = int(rng.integers(0, len(base)))
                base[index] += 8.0 * scale[index]
            vectors = [
                (base + rng.normal(0.0, 0.05, size=len(base)) * scale).tolist()
                for _ in range(window)
            ]
            neural.reset()
            for vector in vectors:
                neural_score = neural.score(vector)
            classical_score = max(classical.score(vector) for vector in vectors)
            forest_score = max(forest_only_score(vector) for vector in vectors)
            rule_z = max(rule_score(vector) for vector in vectors)
            if anomalous:
                anomaly_scores.append(neural_score)
                classical_anomaly.append(classical_score)
                forest_anomaly.append(forest_score)
                rule_anomaly.append(rule_z)
            else:
                normal_scores.append(neural_score)
                classical_normal.append(classical_score)
                forest_normal.append(forest_score)
                rule_normal.append(rule_z)

    neural_threshold = neural.threshold
    classical_threshold = classical.threshold
    forest_threshold = classical_threshold
    rule_threshold = RULE_Z
    return {
        "samples_per_class": samples,
        "seed": seed,
        "neural": {
            "threshold": round(float(neural_threshold), 6),
            "false_alarms": sum(s > neural_threshold for s in normal_scores),
            "detections": sum(s > neural_threshold for s in anomaly_scores),
            "mean_normal_score": round(float(np.mean(normal_scores)), 6),
            "mean_anomaly_score": round(float(np.mean(anomaly_scores)), 6),
        },
        "defender_shipped": {
            "threshold": round(float(classical_threshold), 6),
            "false_alarms": sum(s > classical_threshold for s in classical_normal),
            "detections": sum(s > classical_threshold for s in classical_anomaly),
            "mean_normal_score": round(float(np.mean(classical_normal)), 6),
            "mean_anomaly_score": round(float(np.mean(classical_anomaly)), 6),
        },
        "rule_based_3sigma": {
            "threshold": rule_threshold,
            "false_alarms": sum(s > rule_threshold for s in rule_normal),
            "detections": sum(s > rule_threshold for s in rule_anomaly),
            "mean_normal_score": round(float(np.mean(rule_normal)), 6),
            "mean_anomaly_score": round(float(np.mean(rule_anomaly)), 6),
        },
        "isolation_forest": {
            "threshold": round(float(forest_threshold), 6),
            "false_alarms": sum(s > forest_threshold for s in forest_normal),
            "detections": sum(s > forest_threshold for s in forest_anomaly),
            "mean_normal_score": round(float(np.mean(forest_normal)), 6),
            "mean_anomaly_score": round(float(np.mean(forest_anomaly)), 6),
        },
        "note": (
            "Holdout samples are seeded perturbations of the committed baseline; "
            "they are synthetic and are not v1.1 experimental evidence. All four "
            "detectors score the same 30 normal and 30 anomalous windows."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.deep_validation")
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--out", default="ml/deep/validation.json")
    args = parser.parse_args(argv)

    payload = {
        "version": "v1.2-deep-aiml",
        "attacker": compare_attackers(episodes=args.episodes),
        "defender": compare_defenders(samples=args.samples),
        "caveats": [
            "Synthetic holdout data; no live Kubernetes trials were run.",
            "v1.1 raw trials and statistics remain immutable.",
        ],
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
