"""Defender-owned kubectl wrapper (kept separate from the attacker package)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class KubectlError(RuntimeError):
    """Raised when kubectl exits with a non-zero status."""


def kubectl_path() -> str:
    override = os.environ.get("KUBECTL")
    if override:
        return override
    name = "kubectl.exe" if os.name == "nt" else "kubectl"
    local = REPO_ROOT / "tools" / "bin" / name
    return str(local) if local.exists() else "kubectl"


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [kubectl_path(), *args]
    result = subprocess.run(command, text=True, capture_output=True, cwd=REPO_ROOT)
    if check and result.returncode != 0:
        raise KubectlError(
            f"{' '.join(command)} failed ({result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result
