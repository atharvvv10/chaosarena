"""Deploy a deliberately bad payment release, gate it, roll it back, gate again.

The bad release sets `PAYMENT_FAILURE_RATE=1.0`, so every payment fails. The
same short network-latency battle is run through the real controller and gate
while the bad release is live and again after the rollback. The script never
records the result as the headline battle; it writes its own evidence file.

Everything is local and free: kubectl against the existing Kind cluster, the
project's own attacker, defender and gate.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.battle import BattleRunner  # noqa: E402
from controller.gate import evaluate_gate  # noqa: E402
from controller.score import score_battle  # noqa: E402

OUTPUT = ROOT / "ml" / "bad_release_experiment.json"
ATTACK_LOG = ROOT / "ml" / "bad_release_attack.json"
NAMESPACE = "shop-test"
SERVICE = "payment-service"
GOOD_FAILURE_RATE = "0.01"
BAD_FAILURE_RATE = "1.0"
KUBECTL = (
    str(ROOT / "tools" / "bin" / ("kubectl.exe" if sys.platform.startswith("win") else "kubectl"))
    if (ROOT / "tools" / "bin" / ("kubectl.exe" if sys.platform.startswith("win") else "kubectl")).exists()
    else (shutil.which("kubectl") or "kubectl")
)


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


def kubectl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [KUBECTL, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def set_failure_rate(value: str) -> None:
    kubectl(
        "-n", NAMESPACE, "set", "env", f"deploy/{SERVICE}",
        f"PAYMENT_FAILURE_RATE={value}",
    )
    kubectl(
        "-n", NAMESPACE, "rollout", "status", f"deploy/{SERVICE}",
        "--timeout=180s",
    )


def wait_normal(limit: float = 180.0, poll: float = 5.0) -> dict:
    deadline = time.monotonic() + limit
    sample = cli("defender.cli", "detect")
    while sample.get("anomaly") and time.monotonic() < deadline:
        time.sleep(poll)
        sample = cli("defender.cli", "detect")
    return sample


def gate_battle(version: str, settle: float = 60.0) -> dict:
    runner = BattleRunner(
        settle_seconds=settle,
        startup_settle_seconds=0.0,
        log_path=ATTACK_LOG,
    )
    result = runner.run(
        attack="network-latency",
        target=SERVICE,
        duration=30,
        version=version,
    )
    scored = score_battle(result)
    decision = evaluate_gate(result, scored, threshold=70)
    return {
        "battle": result.as_dict(),
        "score": scored.as_dict(),
        "decision": decision.as_dict(),
    }


def main() -> int:
    cli("attacker.cli", "cleanup")
    wait_normal()
    original = kubectl(
        "-n", NAMESPACE, "get", "deploy", SERVICE,
        "-o", "jsonpath={.spec.template.spec.containers[0].env[?(@.name==\"PAYMENT_FAILURE_RATE\")].value}",
        check=False,
    ).stdout.strip() or GOOD_FAILURE_RATE

    payload: dict = {
        "service": SERVICE,
        "bad_release": {"change": f"PAYMENT_FAILURE_RATE={BAD_FAILURE_RATE}", "version": "bad-payment-v2"},
        "rollback": {"change": f"PAYMENT_FAILURE_RATE={original}", "version": "payment-v1-rollback"},
        "note": (
            "single pair of local runs; not a statistical study. The bad release makes "
            "every payment fail. The same network-latency battle is scored by the real gate "
            "before and after rollback."
        ),
    }

    try:
        set_failure_rate(BAD_FAILURE_RATE)
        time.sleep(8)
        payload["bad_release"]["evidence"] = gate_battle("bad-payment-v2")

        set_failure_rate(original)
        normal = wait_normal()
        payload["rollback"]["normal_after_rollback"] = normal
        payload["rollback"]["evidence"] = gate_battle("payment-v1-rollback")
    finally:
        set_failure_rate(original)
        cli("attacker.cli", "cleanup")

    blocked = payload["bad_release"]["evidence"]["decision"]["verdict"]
    promoted = payload["rollback"]["evidence"]["decision"]["verdict"]
    payload["result"] = {
        "bad_release_verdict": blocked,
        "rollback_verdict": promoted,
        "gate_caught_bad_release": blocked == "BLOCK" and promoted == "PROMOTE",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
