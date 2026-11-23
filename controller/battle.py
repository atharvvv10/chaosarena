"""Run one complete attack -> defend -> recover battle.

The controller talks to the attacker and defender only through their published
command line interfaces. It cannot reach around their allowlists.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

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


def run_cli(module: str, *args: str, timeout: float | None = None) -> dict:
    """Run `python -m <module> ...` and parse its JSON output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", module, *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ControllerError(
            f"{module} {' '.join(args)} timed out after {timeout}s"
        ) from exc
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


def _finite_float(value: object) -> float | None:
    """Parse a measurement value, rejecting booleans and non-finite numbers."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def recovery_confirmed(final: dict, threshold: float) -> bool:
    """Confirm recovery from a valid final measurement, not an earlier check.

    A verification run during remediation is supporting evidence, but the
    post-cleanup anomaly score is authoritative. Missing, malformed, non-finite
    or wrongly typed measurements cannot prove recovery.
    """
    if not isinstance(final, dict):
        return False
    final_score = _finite_float(final.get("score"))
    effective_threshold = _finite_float(threshold)
    anomaly = final.get("anomaly")
    if final_score is None or effective_threshold is None or not isinstance(anomaly, bool):
        return False
    return final_score <= effective_threshold and not anomaly


class BattleRunner:
    """Drive one allowlisted attack and record what the Defender observed."""

    def __init__(
        self,
        poll_interval: float = 5.0,
        defender_wait: float = 10.0,
        settle_seconds: float = 45.0,
        startup_settle_seconds: float = 90.0,
        log_path: Path | str = ATTACK_LOG,
        command_timeout: float | None = None,
    ) -> None:
        self.poll_interval = poll_interval
        self.defender_wait = defender_wait
        self.settle_seconds = settle_seconds
        self.startup_settle_seconds = startup_settle_seconds
        self.log_path = Path(log_path)
        self.command_timeout = command_timeout

    def run(
        self,
        attack: str = "network-latency",
        target: str = "payment-service",
        duration: int = 30,
        version: str = "candidate",
        remediate: bool = True,
        observe_after_detection: bool = False,
        on_detection: Callable[[float], dict[str, Any] | None] | None = None,
    ) -> BattleResult:
        """Run one battle.

        `remediate=False` keeps detection polling but never diagnoses or acts.
        It is provided for controlled observe-only experiments; the default
        preserves the production Defender path.

        `observe_after_detection=True` continues read-only detection polls until
        the attacker finishes, so validation runs can measure how long the
        anomaly stayed active. `on_detection` is an optional read-only hook that
        records fault-target evidence at the moment of first detection.
        """
        if attack not in KNOWN_ATTACKS:
            raise ControllerError(
                f"unknown attack {attack!r}; choose from {sorted(KNOWN_ATTACKS)}"
            )
        if duration <= 0:
            raise ControllerError("duration must be positive")

        # 1. Clean starting state.
        status = run_cli("attacker.cli", "status", timeout=self.command_timeout)
        if status.get("chaos_objects"):
            run_cli("attacker.cli", "cleanup", timeout=self.command_timeout)

        # 2. What does normal look like to the Defender?
        baseline = run_cli(
            "defender.cli", "detect", timeout=self.command_timeout
        )
        threshold = float(baseline.get("threshold", 0.0))

        # 2b. Wait for a genuinely normal starting point. A previous battle can
        # still sit inside the 30-second Prometheus window, which would make the
        # next battle look "detected" at 0.0 s even though the fault was new.
        deadline = time.monotonic() + self.startup_settle_seconds
        current = baseline
        while (
            float(current.get("score", 0.0)) > threshold
            and time.monotonic() < deadline
        ):
            time.sleep(self.poll_interval)
            current = run_cli(
                "defender.cli", "detect", timeout=self.command_timeout
            )

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
            anomaly_observations: list[dict[str, Any]] = []
            detection_evidence: dict[str, Any] | None = None
            detection_elapsed: float | None = None
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > duration + 10:
                    break
                current = run_cli(
                    "defender.cli", "detect", timeout=self.command_timeout
                )
                anomaly = bool(current.get("anomaly"))
                score = _finite_float(current.get("score"))
                if detected or anomaly:
                    anomaly_observations.append(
                        {
                            "elapsed_seconds": round(elapsed, 3),
                            "anomaly": anomaly,
                            "score": score,
                        }
                    )
                if anomaly and not detected:
                    detected = True
                    detection_seconds = round(elapsed, 1)
                    detection_elapsed = elapsed
                    if on_detection is not None:
                        detection_evidence = on_detection(elapsed) or None
                    if remediate:
                        defender_output = run_cli(
                            "defender.cli",
                            "run",
                            "--act",
                            "--wait",
                            str(int(self.defender_wait)),
                            timeout=self.command_timeout,
                        )
                    else:
                        defender_output = {
                            "anomaly": True,
                            "observation_only": True,
                            "score": current.get("score"),
                            "threshold": current.get("threshold"),
                        }
                    if not observe_after_detection:
                        break
                time.sleep(self.poll_interval)

            try:
                process.wait(timeout=self.command_timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                attack_error = "attacker process timed out"

            anomaly_times = [
                item["elapsed_seconds"]
                for item in anomaly_observations
                if item["anomaly"]
            ]
            anomaly_active_seconds: float | None = None
            if len(anomaly_times) >= 2:
                anomaly_active_seconds = round(
                    max(anomaly_times) - min(anomaly_times), 3
                )
            elif anomaly_times:
                anomaly_active_seconds = 0.0
            first_normal_after_detection_seconds: float | None = None
            effective_threshold = _finite_float(threshold)
            if detected and detection_elapsed is not None and effective_threshold is not None:
                first_normal_after_detection_seconds = next(
                    (
                        item["elapsed_seconds"]
                        for item in anomaly_observations
                        if item["elapsed_seconds"] > detection_elapsed
                        and not item["anomaly"]
                        and item["score"] is not None
                        and item["score"] <= effective_threshold
                    ),
                    None,
                )

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
        status = run_cli(
            "attacker.cli", "status", timeout=self.command_timeout
        )
        chaos_remaining = len(status.get("chaos_objects", []))
        final = run_cli("defender.cli", "detect", timeout=self.command_timeout)
        deadline = time.monotonic() + self.settle_seconds
        final_score = _finite_float(final.get("score"))
        while (
            final_score is not None
            and final_score > threshold
            and time.monotonic() < deadline
        ):
            time.sleep(self.poll_interval)
            final = run_cli(
                "defender.cli", "detect", timeout=self.command_timeout
            )
            final_score = _finite_float(final.get("score"))
        recovered = recovery_confirmed(final, threshold)
        recovery_seconds: float | None = None
        if recovered:
            recovery_seconds = round(time.monotonic() - started, 1)


        return BattleResult(
            attack=attack,
            target=target,
            version=version,
            detected=detected,
            detection_seconds=detection_seconds,
            recovery_seconds=recovery_seconds,
            recovered=recovered,
            final_score=final_score,
            defender_threshold=threshold,
            cleanup_ok=bool(attack_output.get("cleanup_ok")),
            chaos_objects_remaining=chaos_remaining,
            diagnosis=defender_output.get("diagnosis"),
            action_taken=defender_output.get("action_taken"),
            attack_error=attack_error,
            detection_evidence=detection_evidence,
            anomaly_observations=anomaly_observations if observe_after_detection else None,
            anomaly_active_seconds=(
                anomaly_active_seconds if observe_after_detection else None
            ),
            first_normal_after_detection_seconds=(
                first_normal_after_detection_seconds if observe_after_detection else None
            ),
        )
