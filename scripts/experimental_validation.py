"""Live v1.1 validation harness: repeated trials and frozen-model holdout.

This script runs real trials against the existing isolated Kind lab. It never
fabricates measurements and never retrains or retunes the Defender. It writes
only under `ml/experimental_validation/` and restores the one v1.0 evidence file
that the live Defender path appends to (`ml/defender_actions.jsonl`).

Commands:
    python scripts/experimental_validation.py run --trials 10
    python scripts/experimental_validation.py holdout --samples 30
    python scripts/experimental_validation.py summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controller.battle import BattleRunner  # noqa: E402
from controller.gate import DEFAULT_THRESHOLD, evaluate_gate  # noqa: E402
from controller.score import score_battle  # noqa: E402
from defender.collect import DEFAULT_BASELINE, prometheus_url, sample_once  # noqa: E402
from defender.features import FEATURE_NAMES, vector_from  # noqa: E402
from defender.model import DEFAULT_MODEL, Detector  # noqa: E402

DEFAULT_DIR = ROOT / "ml" / "experimental_validation"
TRIALS_FILE = DEFAULT_DIR / "trials.jsonl"
HOLDOUT_FILE = DEFAULT_DIR / "holdout_normal.jsonl"
SUMMARY_FILE = DEFAULT_DIR / "summary.json"
BACKUP_DIR = DEFAULT_DIR / "frozen_backup"
FROZEN_HASHES_FILE = DEFAULT_DIR / "frozen_hashes.json"

# These files define the published v1.0 evidence set. The harness only appends
# to defender_actions.jsonl through the unchanged Defender CLI; it hashes all of
# them before and after so preservation is auditable.
FROZEN_FILES = [
    ROOT / "ml" / "last_battle.json",
    ROOT / "ml" / "last_attack.json",
    ROOT / "ml" / "gate_decisions.jsonl",
    ROOT / "ml" / "defender_actions.jsonl",
    ROOT / "ml" / "baseline.csv",
    ROOT / "ml" / "defender_model.joblib",
    ROOT / "ml" / "incident_report.md",
    ROOT / "ml" / "rl_benchmark.json",
    ROOT / "ml" / "defender_benchmark.json",
    ROOT / "ml" / "no_defender_baseline.json",
    ROOT / "ml" / "bad_release_experiment.json",
]
MUTABLE_FROZEN_FILES = [ROOT / "ml" / "defender_actions.jsonl"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_hashes() -> dict[str, str | None]:
    return {display_path(path): sha256_file(path) for path in FROZEN_FILES}


def save_frozen_hashes(hashes: dict[str, str | None]) -> None:
    FROZEN_HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_HASHES_FILE.write_text(
        json.dumps(
            {
                "captured_at": utc_now(),
                "git_head": git_head(),
                "hashes": hashes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_frozen_hashes() -> dict[str, str | None] | None:
    if not FROZEN_HASHES_FILE.exists():
        return None
    payload = json.loads(FROZEN_HASHES_FILE.read_text(encoding="utf-8"))
    hashes = payload.get("hashes")
    return hashes if isinstance(hashes, dict) else None


def git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def cli_json(module: str, *args: str, timeout: float | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = result.stdout.strip()
    if not output:
        detail = " ".join(result.stderr.strip().split())[-400:]
        raise RuntimeError(f"{module} {' '.join(args)} produced no JSON: {detail}")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{module} {' '.join(args)} produced invalid JSON: {output[:300]}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{module} {' '.join(args)} did not return a JSON object")
    return payload


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, indent=None) + "\n" for record in records),
        encoding="utf-8",
    )


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=None) + "\n")


def snapshot_frozen() -> None:
    if BACKUP_DIR.exists():
        raise RuntimeError(
            f"interrupted run detected: {BACKUP_DIR} exists; "
            "run `python scripts/experimental_validation.py restore-frozen` first"
        )
    BACKUP_DIR.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {"created_at": utc_now(), "files": {}}
    for path in MUTABLE_FROZEN_FILES:
        rel = display_path(path)
        existed = path.exists()
        backup = BACKUP_DIR / path.name
        backup.write_bytes(path.read_bytes() if existed else b"")
        manifest["files"][rel] = {"existed": existed, "backup": backup.name}
    (BACKUP_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def restore_frozen() -> None:
    if not BACKUP_DIR.exists():
        print("No frozen-evidence backup to restore.")
        return
    manifest = json.loads((BACKUP_DIR / "manifest.json").read_text(encoding="utf-8"))
    for rel, details in manifest["files"].items():
        path = ROOT / rel
        backup = BACKUP_DIR / details["backup"]
        if details["existed"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(backup.read_bytes())
        elif path.exists():
            path.unlink()
    for child in BACKUP_DIR.iterdir():
        child.unlink()
    BACKUP_DIR.rmdir()
    print(f"Restored {len(manifest['files'])} frozen evidence file(s).")


def check_lab_ready(command_timeout: float) -> None:
    attacker = cli_json("attacker.cli", "ready", timeout=command_timeout)
    defender = cli_json("defender.cli", "ready", timeout=command_timeout)
    status = cli_json("attacker.cli", "status", timeout=command_timeout)
    if not attacker.get("ready"):
        raise RuntimeError(f"attacker lab not ready: {attacker}")
    if not defender.get("ready"):
        raise RuntimeError(f"prometheus not ready: {defender}")
    if status.get("chaos_objects"):
        raise RuntimeError(f"active chaos objects before experiment: {status['chaos_objects']}")
    print(f"Lab ready: {attacker['namespace']}, {defender['url']}, no active chaos.")


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def run_trials(args: argparse.Namespace) -> int:
    trials_file = Path(args.trials)
    if args.fresh and trials_file.exists():
        trials_file.unlink()
    check_lab_ready(args.command_timeout)
    before = frozen_hashes()
    save_frozen_hashes(before)
    snapshot_frozen()

    existing = load_jsonl(trials_file)
    configured = {
        (record.get("trial"), record.get("configuration"))
        for record in existing
        if record.get("status") in {
            "completed",
            "completed_with_attacker_error",
            "inconclusive_no_detection",
            "error",
        }
    }

    restored = False
    try:
        for trial in range(1, args.trial_count + 1):
            modes = (
                ["defender-enabled", "observe-only"]
                if trial % 2 == 1
                else ["observe-only", "defender-enabled"]
            )
            for order_index, mode in enumerate(modes):
                key = (trial, mode)
                if key in configured:
                    print(f"skip existing trial {trial:02d} {mode}")
                    continue

                version = f"v1.1-{mode}-{trial:02d}"
                log_path = DEFAULT_DIR / "attacker_logs" / f"{version}.json"
                record: dict[str, Any] = {
                    "trial": trial,
                    "order_in_pair": order_index + 1,
                    "configuration": mode,
                    "version": version,
                    "attack": args.attack,
                    "target": args.target,
                    "duration_seconds": args.duration,
                    "poll_seconds": args.poll,
                    "started_at": utc_now(),
                    "status": "running",
                    "git_head": git_head(),
                    "model_sha256": sha256_file(ROOT / DEFAULT_MODEL),
                    "baseline_sha256": sha256_file(ROOT / DEFAULT_BASELINE),
                }
                existing.append(record)
                write_jsonl(trials_file, existing)
                print(f"trial {trial:02d} {mode}: attack starting")

                try:
                    runner = BattleRunner(
                        poll_interval=args.poll,
                        defender_wait=args.defender_wait,
                        settle_seconds=args.settle,
                        startup_settle_seconds=args.startup_settle,
                        log_path=log_path,
                        command_timeout=args.command_timeout,
                    )
                    battle = runner.run(
                        attack=args.attack,
                        target=args.target,
                        duration=args.duration,
                        version=version,
                        remediate=(mode == "defender-enabled"),
                    )
                    scored = score_battle(battle)
                    decision = evaluate_gate(
                        battle, scored, threshold=args.gate_threshold
                    )
                    status = "completed"
                    if battle.attack_error:
                        status = "completed_with_attacker_error"
                    if not battle.detected:
                        status = "inconclusive_no_detection"

                    record.update(
                        {
                            "status": status,
                            "detected": battle.detected,
                            "detection_seconds": battle.detection_seconds,
                            "recovered": battle.recovered,
                            "recovery_seconds": battle.recovery_seconds,
                            "final_score": battle.final_score,
                            "defender_threshold": battle.defender_threshold,
                            "cleanup_ok": battle.cleanup_ok,
                            "chaos_objects_remaining": battle.chaos_objects_remaining,
                            "attack_error": battle.attack_error,
                            "diagnosis": battle.diagnosis,
                            "action_taken": battle.action_taken,
                            "defender_action_occurred": battle.action_taken is not None,
                            "score": scored.score,
                            "grade": scored.grade,
                            "deductions": scored.deductions,
                            "gate_verdict": decision.verdict,
                            "gate_reasons": decision.reasons,
                            "attacker_log": str(log_path.relative_to(ROOT)),
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - every failure is a trial result
                    record.update(
                        {
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

                record["ended_at"] = utc_now()
                existing[-1] = record
                write_jsonl(trials_file, existing)
                print(
                    f"trial {trial:02d} {mode}: {record['status']} "
                    f"detected={record.get('detected')} "
                    f"recovery={record.get('recovery_seconds')} "
                    f"gate={record.get('gate_verdict')}"
                )

        restore_frozen()
        restored = True
        after = frozen_hashes()
        write_summary(trials_file, Path(args.holdout), Path(args.summary), before, after)
        changed = [name for name in before if before[name] != after[name]]
        if changed:
            raise RuntimeError(f"frozen evidence changed after experiment: {changed}")
        return 0
    finally:
        if not restored:
            restore_frozen()


def collect_holdout(args: argparse.Namespace) -> int:
    holdout_file = Path(args.holdout)
    if args.fresh and holdout_file.exists():
        holdout_file.unlink()
    if args.interval < 31:
        raise ValueError(
            "interval must be at least 31 s so 30 s Prometheus windows do not overlap"
        )

    status = cli_json("attacker.cli", "status", timeout=args.command_timeout)
    if status.get("chaos_objects"):
        raise RuntimeError(f"active chaos objects before holdout: {status['chaos_objects']}")

    detector = Detector.load(str(ROOT / DEFAULT_MODEL))
    model_hash = sha256_file(ROOT / DEFAULT_MODEL)
    baseline_hash = sha256_file(ROOT / DEFAULT_BASELINE)

    for sample_number in range(1, args.samples + 1):
        chaos = cli_json("attacker.cli", "status", timeout=args.command_timeout)
        if chaos.get("chaos_objects"):
            raise RuntimeError(
                f"chaos appeared during holdout collection: {chaos['chaos_objects']}"
            )
        vector = vector_from(sample_once())
        score = detector.score(vector)
        record = {
            "sample": sample_number,
            "timestamp": utc_now(),
            "dataset": "held-out-normal",
            "window": "30s",
            "valid": chaos.get("chaos_objects") == []
            and vector[FEATURE_NAMES.index("loadgen_request_rate")] > 0,
            "features": {
                name: round(value, 6) for name, value in zip(FEATURE_NAMES, vector)
            },
            "score": round(score, 6),
            "threshold": round(detector.threshold, 6),
            "anomaly": bool(score > detector.threshold),
            "chaos_objects": chaos.get("chaos_objects", []),
            "prometheus_url": prometheus_url(),
            "model_sha256": model_hash,
            "baseline_sha256": baseline_hash,
            "training_split": (
                "frozen model fitted on ml/baseline.csv only; this sample was not "
                "used for training or threshold selection"
            ),
        }
        append_jsonl(holdout_file, record)
        print(
            f"holdout {sample_number:02d}/{args.samples}: "
            f"score={record['score']} anomaly={record['anomaly']}"
        )
        if sample_number < args.samples:
            time.sleep(args.interval)

    write_summary(
        Path(args.trials), holdout_file, Path(args.summary), None, frozen_hashes()
    )
    return 0


def _stats(values: list[float]) -> dict[str, float | int | None]:
    clean = [value for value in values if _finite(value) is not None]
    if not clean:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "range": None,
            "stdev": None,
            "q1": None,
            "q3": None,
            "iqr": None,
        }
    ordered = sorted(clean)
    q1 = statistics.median(ordered[: max(1, len(ordered) // 2)])
    q3 = statistics.median(ordered[(len(ordered) + 1) // 2 :]) if len(ordered) > 1 else q1
    return {
        "count": len(clean),
        "mean": round(statistics.fmean(clean), 2),
        "median": round(statistics.median(clean), 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "range": round(ordered[-1] - ordered[0], 2),
        "stdev": round(statistics.stdev(clean), 2) if len(clean) > 1 else 0.0,
        "q1": round(q1, 2),
        "q3": round(q3, 2),
        "iqr": round(q3 - q1, 2),
    }


def _configuration_summary(records: list[dict]) -> dict[str, Any]:
    attempted = len(records)
    terminal = [record for record in records if record.get("status") != "running"]
    detected = [record for record in terminal if record.get("detected") is True]
    recovered = [record for record in terminal if record.get("recovered") is True]
    gate_counts = Counter(record.get("gate_verdict") for record in terminal)
    return {
        "attempted": attempted,
        "terminal": len(terminal),
        "status_counts": dict(Counter(record.get("status") for record in terminal)),
        "detected": len(detected),
        "detection_rate": round(len(detected) / len(terminal), 3) if terminal else None,
        "detection_seconds": _stats(
            [record.get("detection_seconds") for record in detected]
        ),
        "recovered": len(recovered),
        "recovery_rate_of_terminal": (
            round(len(recovered) / len(terminal), 3) if terminal else None
        ),
        "recovery_rate_of_detected": (
            round(
                len(
                    [
                        record
                        for record in recovered
                        if record.get("detected") is True
                    ]
                )
                / len(detected),
                3,
            )
            if detected
            else None
        ),
        "recovery_seconds": _stats(
            [record.get("recovery_seconds") for record in recovered]
        ),
        "defender_actions": sum(
            1 for record in terminal if record.get("defender_action_occurred") is True
        ),
        "final_anomaly_score": _stats(
            [record.get("final_score") for record in terminal]
        ),
        "gate_verdicts": dict(gate_counts),
    }


def write_summary(
    trials_file: Path,
    holdout_file: Path,
    output: Path,
    frozen_before: dict[str, str | None] | None,
    frozen_after: dict[str, str | None] | None,
) -> dict:
    trials = load_jsonl(trials_file)
    holdout = load_jsonl(holdout_file)
    if frozen_before is None:
        frozen_before = load_frozen_hashes()
    configurations = {
        mode: _configuration_summary(
            [record for record in trials if record.get("configuration") == mode]
        )
        for mode in ["defender-enabled", "observe-only"]
    }

    by_trial: dict[int, dict[str, dict]] = {}
    for record in trials:
        by_trial.setdefault(int(record["trial"]), {})[record["configuration"]] = record
    paired_deltas: list[float] = []
    for trial, modes in by_trial.items():
        enabled = modes.get("defender-enabled", {}).get("recovery_seconds")
        observed = modes.get("observe-only", {}).get("recovery_seconds")
        enabled_value = _finite(enabled)
        observed_value = _finite(observed)
        if enabled_value is not None and observed_value is not None:
            paired_deltas.append(round(observed_value - enabled_value, 2))

    valid_holdout = [record for record in holdout if record.get("valid") is True]
    false_positives = sum(1 for record in valid_holdout if record.get("anomaly") is True)
    fpr = false_positives / len(valid_holdout) if valid_holdout else None
    # Exact one-sided 95% Clopper-Pearson upper bound; useful when FP count is 0.
    upper_bound = (
        1.0 - 0.05 ** (1.0 / len(valid_holdout)) if valid_holdout else None
    )

    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "git_head": git_head(),
        "trial_records": len(trials),
        "holdout_records": len(holdout),
        "configurations": configurations,
        "paired_recovery_delta_seconds": {
            "definition": "observe-only recovery minus defender-enabled recovery; positive means Defender-enabled recovered sooner",
            **_stats(paired_deltas),
            "positive_pairs": sum(1 for value in paired_deltas if value > 0),
            "negative_pairs": sum(1 for value in paired_deltas if value < 0),
        },
        "holdout_normal": {
            "collected": len(holdout),
            "valid": len(valid_holdout),
            "false_positives": false_positives,
            "false_positive_rate": round(fpr, 6) if fpr is not None else None,
            "one_sided_95_upper_bound": (
                round(upper_bound, 6) if upper_bound is not None else None
            ),
            "score": _stats([record.get("score") for record in valid_holdout]),
            "model_sha256": sha256_file(ROOT / DEFAULT_MODEL),
            "baseline_sha256": sha256_file(ROOT / DEFAULT_BASELINE),
        },
        "frozen_evidence": {
            "before": frozen_before,
            "after": frozen_after
            or {name: sha256_file(ROOT / name) for name in (frozen_before or {})},
        },
        "source_files": {
            "trials": display_path(trials_file),
            "holdout": display_path(holdout_file),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {display_path(output)}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run paired live trials")
    run.add_argument("--trials", type=int, dest="trial_count", default=10)
    run.add_argument("--attack", default="cpu-stress")
    run.add_argument("--target", default="order-service")
    run.add_argument("--duration", type=int, default=120)
    run.add_argument("--poll", type=float, default=3.0)
    run.add_argument("--settle", type=float, default=180.0)
    run.add_argument("--startup-settle", type=float, default=180.0)
    run.add_argument("--defender-wait", type=float, default=10.0)
    run.add_argument("--command-timeout", type=float, default=240.0)
    run.add_argument("--gate-threshold", type=int, default=DEFAULT_THRESHOLD)
    run.add_argument("--trials-file", dest="trials", default=str(TRIALS_FILE))
    run.add_argument("--holdout-file", dest="holdout", default=str(HOLDOUT_FILE))
    run.add_argument("--summary-file", dest="summary", default=str(SUMMARY_FILE))
    run.add_argument("--fresh", action="store_true", help="discard existing trial records")
    run.set_defaults(func=run_trials)

    holdout = sub.add_parser("holdout", help="collect frozen-model normal holdout")
    holdout.add_argument("--samples", type=int, default=30)
    holdout.add_argument("--interval", type=float, default=35.0)
    holdout.add_argument("--command-timeout", type=float, default=60.0)
    holdout.add_argument("--trials-file", dest="trials", default=str(TRIALS_FILE))
    holdout.add_argument("--holdout-file", dest="holdout", default=str(HOLDOUT_FILE))
    holdout.add_argument("--summary-file", dest="summary", default=str(SUMMARY_FILE))
    holdout.add_argument("--fresh", action="store_true", help="discard existing holdout records")
    holdout.set_defaults(func=collect_holdout)

    summary = sub.add_parser("summary", help="recompute summary from committed files")
    summary.add_argument("--trials-file", dest="trials", default=str(TRIALS_FILE))
    summary.add_argument("--holdout-file", dest="holdout", default=str(HOLDOUT_FILE))
    summary.add_argument("--summary-file", dest="summary", default=str(SUMMARY_FILE))
    def _summary(args: argparse.Namespace) -> int:
        write_summary(
            Path(args.trials),
            Path(args.holdout),
            Path(args.summary),
            None,
            None,
        )
        return 0

    summary.set_defaults(func=_summary)

    restore = sub.add_parser("restore-frozen", help="restore v1.0 evidence after interruption")
    restore.set_defaults(func=lambda args: restore_frozen())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
