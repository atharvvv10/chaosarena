"""Command line: python -m controller.cli <command>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .battle import KNOWN_ATTACKS, BattleRunner
from .evidence import record_battle
from .gate import DEFAULT_THRESHOLD, evaluate_gate, last_decision, record_decision
from .score import BattleResult, score_battle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m controller.cli",
        description="Phase 4 Arena Controller: battle, resilience score and release gate.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guard", help="print the controller's hard boundaries")

    evaluate = sub.add_parser("evaluate", help="run a battle and decide on promotion")
    evaluate.add_argument("--attack", choices=sorted(KNOWN_ATTACKS), default="network-latency")
    evaluate.add_argument("--target", default="payment-service")
    evaluate.add_argument("--duration", type=int, default=30)
    evaluate.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    evaluate.add_argument("--settle", type=int, default=45, help="seconds to wait for metrics to settle")
    evaluate.add_argument("--version", default="candidate")

    score = sub.add_parser("score", help="score a saved battle JSON file")
    score.add_argument("result", help="path to a JSON BattleResult")

    sub.add_parser("last", help="show the last recorded gate decision")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "guard":
        print(json.dumps({
            "known_attacks": sorted(KNOWN_ATTACKS),
            "default_threshold": DEFAULT_THRESHOLD,
            "attacker_interface": "attacker.cli",
            "defender_interface": "defender.cli",
            "imports_attacker_or_defender_modules": False,
        }, indent=2))
        return 0

    if args.command == "evaluate":
        result = BattleRunner(settle_seconds=args.settle).run(
            attack=args.attack,
            target=args.target,
            duration=args.duration,
            version=args.version,
        )
        scored = score_battle(result)
        decision = evaluate_gate(result, scored, threshold=args.threshold)
        record_decision(decision)
        payload = {
            "battle": result.as_dict(),
            "score": scored.as_dict(),
            "decision": decision.as_dict(),
        }
        record_battle(payload)
        print(json.dumps(payload, indent=2))
        return 0 if decision.promote else 1

    if args.command == "score":
        payload = json.loads(Path(args.result).read_text(encoding="utf-8"))
        scored = score_battle(BattleResult(**payload))
        print(json.dumps(scored.as_dict(), indent=2))
        return 0

    if args.command == "last":
        decision = last_decision()
        print(json.dumps({"decision": decision}, indent=2))
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
