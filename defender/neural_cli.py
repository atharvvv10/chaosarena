"""Command line for the deep defender: python -m defender.neural_cli."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collect import load_baseline
from .features import FEATURE_NAMES
from .neural import DEFAULT_MODEL, NeuralDetector


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m defender.neural_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="train the LSTM autoencoder on the baseline CSV")
    train.add_argument("--data", default="ml/baseline.csv")
    train.add_argument("--out", default=str(DEFAULT_MODEL))
    train.add_argument("--epochs", type=int, default=200)
    train.add_argument("--window", type=int, default=8)
    train.add_argument("--seed", type=int, default=42)

    detect = sub.add_parser("detect", help="score one 18-value feature vector")
    detect.add_argument("--model", default=str(DEFAULT_MODEL))
    detect.add_argument("--vector", required=True, help="JSON array of 18 numbers")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "train":
        detector = NeuralDetector(window=args.window, seed=args.seed)
        metrics = detector.train(load_baseline(args.data), epochs=args.epochs)
        path = detector.save(args.out)
        print(json.dumps({**metrics, "saved_to": str(path)}, indent=2))
        return 0

    if args.command == "detect":
        try:
            vector = json.loads(args.vector)
        except json.JSONDecodeError as exc:
            print(f"invalid vector JSON: {exc}", file=sys.stderr)
            return 2
        detector = NeuralDetector.load(Path(args.model))
        score = detector.score(vector)
        print(json.dumps({
            "score": score,
            "threshold": detector.threshold,
            "anomaly": score > detector.threshold,
            "features": len(FEATURE_NAMES),
        }, indent=2))
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
