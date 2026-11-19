"""Command line: python -m defender.cli <command>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import actions
from .actions import ALLOWED_NAMESPACE, ALLOWED_SERVICES, MAX_REPLICAS
from .collect import DEFAULT_BASELINE, collect_baseline, load_baseline, sample_once
from .diagnose import diagnose
from .features import FEATURE_NAMES, vector_from
from .model import DEFAULT_MODEL, Detector, baseline_stats
from .policy import choose_action
from .verify import verify


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m defender.cli",
        description="Phase 3 defender: Isolation Forest detect/diagnose/act/verify.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guard", help="print the defender's hard action allowlist")

    baseline = sub.add_parser("baseline", help="collect normal traffic into CSV")
    baseline.add_argument("--samples", type=int, default=40)
    baseline.add_argument("--interval", type=float, default=5.0)
    baseline.add_argument("--window", default="30s")
    baseline.add_argument("--out", default=str(DEFAULT_BASELINE))

    train = sub.add_parser("train", help="train the Isolation Forest")
    train.add_argument("--data", default=str(DEFAULT_BASELINE))
    train.add_argument("--out", default=str(DEFAULT_MODEL))

    detect = sub.add_parser("detect", help="score the current traffic sample")
    detect.add_argument("--model", default=str(DEFAULT_MODEL))

    diag = sub.add_parser("diagnose", help="explain the current anomaly")
    diag.add_argument("--model", default=str(DEFAULT_MODEL))
    diag.add_argument("--data", default=str(DEFAULT_BASELINE))

    act = sub.add_parser("act", help="run one bounded remediation")
    act.add_argument("action", choices=["restart", "scale"])
    act.add_argument("service")
    act.add_argument("--replicas", type=int)

    ver = sub.add_parser("verify", help="check whether the score returned to normal")
    ver.add_argument("--model", default=str(DEFAULT_MODEL))
    ver.add_argument("--wait", type=float, default=10.0)

    run = sub.add_parser("run", help="full detect -> diagnose -> act -> verify loop")
    run.add_argument("--model", default=str(DEFAULT_MODEL))
    run.add_argument("--data", default=str(DEFAULT_BASELINE))
    run.add_argument("--act", action="store_true", help="allow remedial actions")
    run.add_argument("--wait", type=float, default=10.0)
    return parser


def _load_detector(path: str) -> Detector:
    if not Path(path).exists():
        raise SystemExit(f"model not found at {path}; run 'defender.cli train' first")
    return Detector.load(path)


def _load_stats(path: str):
    if not Path(path).exists():
        raise SystemExit(f"baseline not found at {path}; run 'defender.cli baseline' first")
    return baseline_stats(load_baseline(path))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "guard":
        print(json.dumps({
            "namespace": ALLOWED_NAMESPACE,
            "services": sorted(ALLOWED_SERVICES),
            "min_replicas": actions.MIN_REPLICAS,
            "max_replicas": MAX_REPLICAS,
            "feature_count": len(FEATURE_NAMES),
        }, indent=2))
        return 0

    if args.command == "baseline":
        path = collect_baseline(args.samples, args.interval, args.out, args.window)
        print(json.dumps({"baseline": str(path), "samples": args.samples}, indent=2))
        return 0

    if args.command == "train":
        detector = Detector.train(load_baseline(args.data))
        detector.save(args.out)
        print(json.dumps({
            "model": str(args.out),
            "threshold": round(detector.threshold, 4),
            "features": len(detector.feature_names),
        }, indent=2))
        return 0

    if args.command == "detect":
        detector = _load_detector(args.model)
        vector = vector_from(sample_once())
        score = detector.score(vector)
        print(json.dumps({
            "score": round(score, 4),
            "threshold": round(detector.threshold, 4),
            "anomaly": score > detector.threshold,
        }, indent=2))
        return 0

    if args.command == "diagnose":
        detector = _load_detector(args.model)
        mean, std = _load_stats(args.data)
        result = diagnose(vector_from(sample_once()), mean, std)
        print(json.dumps(result.as_dict(), indent=2))
        return 0

    if args.command == "act":
        entry = actions.apply(args.action, args.service, args.replicas)
        print(json.dumps(entry, indent=2))
        return 0

    if args.command == "verify":
        detector = _load_detector(args.model)
        vector = vector_from(sample_once())
        result = verify(detector, vector, wait=args.wait)
        print(json.dumps(result.as_dict(), indent=2))
        return 0 if result.recovered else 1

    if args.command == "run":
        detector = _load_detector(args.model)
        mean, std = _load_stats(args.data)
        vector = vector_from(sample_once())
        score = detector.score(vector)
        if score <= detector.threshold:
            print(json.dumps({
                "anomaly": False,
                "score": round(score, 4),
                "threshold": round(detector.threshold, 4),
            }, indent=2))
            return 0

        result = diagnose(vector, mean, std)
        decision = choose_action(result)
        entry = None
        if args.act and decision["action"] != "none":
            entry = actions.apply(
                str(decision["action"]),
                str(decision["service"]),
                decision.get("replicas"),
            )
        verification = verify(detector, vector, wait=args.wait)
        print(json.dumps({
            "anomaly": True,
            "score": round(score, 4),
            "threshold": round(detector.threshold, 4),
            "diagnosis": result.as_dict(),
            "decision": decision,
            "action_taken": entry,
            "verification": verification.as_dict(),
        }, indent=2))
        return 0 if verification.recovered else 1

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
