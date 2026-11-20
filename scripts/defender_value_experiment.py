"""Compare the same fault with and without one Defender remediation.

Both variants use the same attacker CLI, target, duration and polling clock.
The "without" variant only calls `defender.cli detect`; it never diagnoses,
acts or verifies. The "with" variant calls `defender.cli run --act` once when
the anomaly is first seen, which performs the normal diagnose/act/verify loop.

This is a single pair of local runs, not a statistical study. The result is
written to `ml/defender_value_experiment.json`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ml" / "defender_value_experiment.json"


def cli(module: str, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError(
            f"{module} {' '.join(args)} produced no JSON: {result.stderr.strip()[-400:]}"
        )
    return json.loads(output)


def detect() -> dict:
    return cli("defender.cli", "detect")


def cleanup() -> dict:
    cli("attacker.cli", "cleanup")
    return cli("attacker.cli", "status")


def wait_normal(limit: float = 150.0, poll: float = 3.0) -> dict:
    deadline = time.monotonic() + limit
    sample = detect()
    while sample.get("anomaly") and time.monotonic() < deadline:
        time.sleep(poll)
        sample = detect()
    return sample


def run_variant(
    *,
    remediate: bool,
    attack: str,
    target: str,
    duration: int,
    poll: float,
    settle: float,
) -> dict:
    cleanup()
    before = wait_normal()
    threshold = float(before["threshold"])

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "attacker.cli",
            "attack",
            attack,
            "--target",
            target,
            "--duration",
            str(duration),
            "--hold",
            str(duration),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    started = time.monotonic()
    detected = False
    detection_seconds: float | None = None
    recovered = False
    recovery_seconds: float | None = None
    diagnosis: dict | None = None
    action_taken: dict | None = None
    final_score = float(before["score"])

    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            sample = detect()
            final_score = float(sample["score"])
            if not detected and sample.get("anomaly"):
                detected = True
                detection_seconds = round(elapsed, 1)
                if remediate:
                    result = cli("defender.cli", "run", "--act", "--wait", "10")
                    diagnosis = result.get("diagnosis")
                    action_taken = result.get("action_taken")
                    final_score = float(result.get("score", final_score))
            if detected and not sample.get("anomaly"):
                recovered = True
                recovery_seconds = round(elapsed, 1)
                break
            time.sleep(poll)

        attack_output = process.communicate(timeout=settle)[0].strip()
        if detected and not recovered:
            deadline = time.monotonic() + settle
            while time.monotonic() < deadline:
                elapsed = time.monotonic() - started
                sample = detect()
                final_score = float(sample["score"])
                if not sample.get("anomaly"):
                    recovered = True
                    recovery_seconds = round(elapsed, 1)
                    break
                time.sleep(poll)
    finally:
        if process.poll() is None:
            process.kill()
        final_status = cleanup()
        after = detect()

    return {
        "defender_remediation": remediate,
        "detected": detected,
        "detection_seconds": detection_seconds,
        "recovered": recovered,
        "recovery_seconds": recovery_seconds,
        "final_score": round(final_score, 4),
        "defender_threshold": threshold,
        "diagnosis": diagnosis,
        "action_taken": action_taken,
        "cleanup_ok": not final_status.get("chaos_objects"),
        "chaos_objects_remaining": len(final_status.get("chaos_objects", [])),
        "score_after": round(float(after["score"]), 4),
        "attacker_output": attack_output[-1000:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack", default="cpu-stress")
    parser.add_argument("--target", default="order-service")
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--poll", type=float, default=3.0)
    parser.add_argument("--settle", type=float, default=120.0)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)

    with_remediation = run_variant(
        remediate=True,
        attack=args.attack,
        target=args.target,
        duration=args.duration,
        poll=args.poll,
        settle=args.settle,
    )
    without_remediation = run_variant(
        remediate=False,
        attack=args.attack,
        target=args.target,
        duration=args.duration,
        poll=args.poll,
        settle=args.settle,
    )

    with_recovery = with_remediation.get("recovery_seconds")
    without_recovery = without_remediation.get("recovery_seconds")
    delta = None
    interpretation = "one or both variants did not recover, so no timing comparison is possible"
    if with_recovery is not None and without_recovery is not None:
        delta = round(float(without_recovery) - float(with_recovery), 1)
        if delta > 5:
            interpretation = (
                f"with the Defender recovered {delta} s sooner in this pair of runs"
            )
        elif delta < -5:
            interpretation = (
                f"with the Defender recovered {abs(delta)} s later in this pair of runs"
            )
        else:
            interpretation = (
                "recovery times were within one polling interval, so this fault does not "
                "show a Defender speed-up"
            )

    payload = {
        "attack": args.attack,
        "target": args.target,
        "duration": args.duration,
        "poll_seconds": args.poll,
        "detection_basis": "seconds since attacker launch until first anomaly observation",
        "note": (
            "single pair of local runs; not a statistical study. Both variants use the "
            "same attacker, target, duration and polling clock. The no-Defender variant "
            "only polls detect; it never diagnoses, acts or verifies."
        ),
        "with_defender": with_remediation,
        "without_defender": without_remediation,
        "recovery_delta_seconds": delta,
        "interpretation": interpretation,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
