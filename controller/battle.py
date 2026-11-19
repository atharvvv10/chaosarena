"""Run one complete attack -> defend -> recover battle.

The controller talks to the attacker and defender only through their published
command line interfaces. It cannot reach around their allowlists.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .score import BattleResult

REPO_ROOT = Path(__file__).resolve().parents[1]
ATTACK_LOG = REPO_ROOT / "ml" / "last_attack.json"
KNOWN_ATTACKS = frozenset(
    {
        "pod-kill",
        "pod-failure",
        "network-latency",
        "network-loss",
        "network-partition",
        "cpu-stress",
        "memory-stress",
    }
)


class ControllerError(RuntimeError):
    """Raised when a battle step cannot be completed."""


def run_cli(module: str, *args: str) -> dict:
    """Run `python -m <module> ...` and parse its JSON output."""
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    output = result.stdout.strip()
    if not output:
        raise ControllerError(
            f"{module} {' '.join(args)} produced no JSON "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ControllerError(
            f"{module} {' '.join(args)} produced invalid JSON: {output[:300]}"
        ) from exc


class BattleRunner:
    """Drive one allowlisted attack and record what the Defender observed."""

    def __init__(
        self,
        poll_interval: float = 5.0,
        defender_wait: float = 10.0,
        settle_seconds: float = 45.0,
        log_path: Path | str = ATTACK_LOG,
    ) -> None:
        self.poll_interval = poll_interval
        self.defender_wait = defender_wait
        self.settle_seconds = settle_seconds
        self.log_path = Path(log_path)

    def run(
        self,
        attack: str = "network-latency",
        target: str = "payment-service",
        duration: int = 30,
        version: str = "candidate",
    ) -> BattleResult:
        if attack not in KNOWN_ATTACKS:
            raise ControllerError(
                f"unknown attack {attack!r}; choose from {sorted(KNOWN_ATTACKS)}"
            )
        if duration <= 0:
            raise ControllerError("duration must be positive")

        # 1. Clean starting state.
        status = run_cli("attacker.cli", "status")
        if status.get("chaos_objects"):
            run_cli("attacker.cli", "cleanup")

        # 2. What does normal look like to the Defender?
        baseline = run_cli("defender.cli", "detect")
        threshold = float(baseline.get("threshold", 0.0))

        # 3. Launch the attack in the background and watch with the Defender.
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        detected = False
        detection_seconds: float | None = None
        defender_output: dict = {}
        attack_output: dict = {}
        attack_error: str | None = None

        with self.log_path.open("w", encoding="utf-8") as handle:
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
                cwd=REPO_ROOT,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )

            started = time.monotonic()
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > duration + 10:
                    break
                current = run_cli("defender.cli", "detect")
                if current.get("anomaly"):
                    detected = True
                    detection_seconds = round(elapsed, 1)
                    defender_output = run_cli(
                        "defender.cli",
                        "run",
                        "--act",
                        "--wait",
                        str(int(self.defender_wait)),
                    )
                    break
                time.sleep(self.poll_interval)

            process.wait()
            elapsed = time.monotonic() - started

        try:
            attack_output = json.loads(self.log_path.read_text(encoding="utf-8").strip())
        except (json.JSONDecodeError, OSError):
            attack_error = "attacker output could not be parsed"
        if attack_output.get("error"):
            attack_error = str(attack_output["error"])
        if not attack_output.get("ok") and attack_error is None:
            attack_error = "attacker did not report success"

        # 4. Did everything return to normal and was the fault removed?
        # A 30 s Prometheus window still holds attack data right after cleanup,
        # so allow a bounded settle period before declaring failure.
        status = run_cli("attacker.cli", "status")
        chaos_remaining = len(status.get("chaos_objects", []))
        final = run_cli("defender.cli", "detect")
        deadline = time.monotonic() + self.settle_seconds
        while float(final.get("score", 0.0)) > threshold and time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            final = run_cli("defender.cli", "detect")

        verification = defender_output.get("verification", {})
        recovered = bool(verification.get("recovered")) or not bool(final.get("anomaly"))

        return BattleResult(
            attack=attack,
            target=target,
            version=version,
            detected=detected,
            detection_seconds=detection_seconds,
            recovered=recovered,
            final_score=float(final.get("score", 0.0)),
            defender_threshold=threshold,
            cleanup_ok=bool(attack_output.get("cleanup_ok")),
            chaos_objects_remaining=chaos_remaining,
            diagnosis=defender_output.get("diagnosis"),
            action_taken=defender_output.get("action_taken"),
            attack_error=attack_error,
        )
