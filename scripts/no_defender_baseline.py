"""Run the same fault without any Defender remediation and time natural recovery.

This is an observe-only baseline: the script calls `defender.cli detect` to read
the anomaly score, but never calls `diagnose`, `act`, `run` or `verify`, and the
controller is not involved. It exists to answer whether the Defender's restart
in the gated battle was necessary for recovery.

Everything is local and free. The result is written to
`ml/no_defender_baseline.json`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ml" / "no_defender_baseline.json"
POLL_SECONDS = 2.0
MAX_WAIT = 180.0


def cli(module: str, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError(f"{module} {' '.join(args)} produced no JSON: {result.stderr.strip()}")
    return json.loads(output)


def detect() -> dict:
    return cli("defender.cli", "detect")


def wait_until_normal(limit: float = 60.0) -> None:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if not detect().get("anomaly"):
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError("traffic did not return to normal before the baseline run")


def main() -> None:
    attack = "network-latency"
    target = "payment-service"
    duration = 30
    hold = 30

    status = cli("attacker.cli", "status")
    if status.get("chaos_objects"):
        cli("attacker.cli", "cleanup")
    wait_until_normal()

    normal = detect()
    threshold = normal["threshold"]
    process = subprocess.Popen(
        [sys.executable, "-m", "attacker.cli", "attack", attack,
         "--target", target, "--duration", str(duration), "--hold", str(hold)],
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
    final_score: float | None = None

    try:
        while time.monotonic() - started < MAX_WAIT:
            elapsed = time.monotonic() - started
            sample = detect()
            score = float(sample["score"])
            final_score = round(score, 4)
            if not detected and sample.get("anomaly"):
                detected = True
                detection_seconds = round(elapsed, 1)
            if detected and not sample.get("anomaly"):
                recovered = True
                recovery_seconds = round(elapsed, 1)
                break
            time.sleep(POLL_SECONDS)
    finally:
        attack_output = process.communicate(timeout=MAX_WAIT)[0]
        cli("attacker.cli", "cleanup")
        final_status = cli("attacker.cli", "status")

    payload = {
        "attack": attack,
        "target": target,
        "duration": duration,
        "hold": hold,
        "defender_remediation": False,
        "note": (
            "observe-only baseline: defender.cli detect was polled, but no "
            "diagnose/act/run/verify action was taken and the controller was not used"
        ),
        "detected": detected,
        "detection_seconds": detection_seconds,
        "detection_basis": "seconds since attacker launch until first anomaly observation",
        "recovered": recovered,
        "recovery_seconds": recovery_seconds,
        "final_score": final_score,
        "defender_threshold": threshold,
        "cleanup_ok": not final_status.get("chaos_objects"),
        "chaos_objects_remaining": len(final_status.get("chaos_objects", [])),
        "attacker_output": attack_output.strip()[-1000:],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
