"""Re-check a recorded battle with the real resilience gate.

This module is used by GitHub Actions, but it works locally too. It never
trusts the decision stored in the evidence file: it rebuilds the BattleResult
from the facts, recomputes the score, and runs the same gate as Phase 4.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from controller.gate import DEFAULT_THRESHOLD, evaluate_gate
from controller.score import BattleResult, score_battle

DEFAULT_EVIDENCE = Path("ml/last_battle.json")
WORKFLOW = Path(".github/workflows/ci.yml")


def load_bundle(path: Path | str = DEFAULT_EVIDENCE) -> BattleResult:
    """Load a battle bundle (or a bare BattleResult) into a BattleResult."""
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    battle = payload.get("battle", payload) if isinstance(payload, dict) else payload
    if not isinstance(battle, dict):
        raise ValueError(f"{target} does not contain a battle object")
    allowed = {item.name for item in fields(BattleResult)}
    return BattleResult(**{key: value for key, value in battle.items() if key in allowed})


def check_bundle(
    path: Path | str = DEFAULT_EVIDENCE,
    threshold: int = DEFAULT_THRESHOLD,
    expect: str = "PROMOTE",
) -> dict:
    """Recompute score + gate and compare the verdict with `expect`."""
    battle = load_bundle(path)
    scored = score_battle(battle)
    decision = evaluate_gate(battle, scored, threshold=threshold)
    return {
        "evidence": str(path),
        "expected": expect,
        "verdict": decision.verdict,
        "passed": decision.verdict == expect,
        "score": scored.score,
        "grade": scored.grade,
        "threshold": threshold,
        "deductions": scored.deductions,
        "reasons": decision.reasons,
        "version": decision.version,
        "attack": decision.attack,
        "target": decision.target,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ci.gate",
        description="Phase 6: free CI resilience gate (no cluster, no secrets).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guard", help="print what this gate does and does not need")

    check = sub.add_parser("check", help="re-score evidence and enforce a verdict")
    check.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    check.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    check.add_argument(
        "--expect",
        choices=["PROMOTE", "BLOCK"],
        default="PROMOTE",
        help="verdict that makes this check pass (default: PROMOTE)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "guard":
        print(json.dumps({
            "workflow": str(WORKFLOW),
            "runner": "ubuntu-latest (GitHub Actions free tier)",
            "cluster_required": False,
            "secrets_required": [],
            "paid_actions_required": False,
            "recomputes_score_from_facts": True,
            "trusted_stored_decision": False,
            "default_expectation": "PROMOTE",
        }, indent=2))
        return 0

    if args.command == "check":
        result = check_bundle(args.evidence, args.threshold, args.expect)
        print(json.dumps(result, indent=2))
        if not result["passed"]:
            print(
                f"GATE FAILED: expected {result['expected']}, got {result['verdict']}",
                file=sys.stderr,
            )
            return 1
        print(
            f"GATE PASSED: {result['verdict']} "
            f"(score {result['score']}, threshold {result['threshold']})"
        )
        return 0

    _parser().error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
