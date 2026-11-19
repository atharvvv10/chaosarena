"""One local command that verifies the whole free project.

Runs only cluster-free checks: Python tests, safety guards, CI gate fixtures and
the React production build. Real cluster battles are phase-specific and are not
replayed here.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(name: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"\n=== {name} ===")
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(f"FAILED: {name} (exit {result.returncode})")
    print(f"OK: {name}")


def main() -> int:
    run("All pytest suites", [PY, "-m", "pytest", "-q"])
    run("CI safety guard", [PY, "-m", "ci.gate", "guard"])
    run("Controller guard", [PY, "-m", "controller.cli", "guard"])
    run("Attacker guard", [PY, "-m", "attacker.cli", "guard"])
    run("Defender guard", [PY, "-m", "defender.cli", "guard"])
    run("RL attacker guard", [PY, "-m", "rl.cli", "guard"])
    run(
        "Bad battle must BLOCK",
        [PY, "-m", "ci.gate", "check", "--evidence", "ci/fixtures/failing_battle.json",
         "--threshold", "70", "--expect", "BLOCK"],
    )
    run(
        "Committed battle must PROMOTE",
        [PY, "-m", "ci.gate", "check", "--evidence", "ml/last_battle.json",
         "--threshold", "70", "--expect", "PROMOTE"],
    )

    npm = shutil.which("npm")
    if npm:
        run("React production build", [npm, "run", "build"], cwd=ROOT / "dashboard")
    else:
        print("\nSKIP: React build (npm not installed)")

    print("\nALL VERIFICATION STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
