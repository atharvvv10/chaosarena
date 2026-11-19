"""Small kubectl wrapper used by the attacker.

Using the CLI instead of a Python Kubernetes client keeps the project light:
the same kubectl binary already used by the rest of the demo is reused, and the
host kubeconfig is honoured without extra configuration.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAOS_KINDS = "podchaos,networkchaos,stresschaos"


class KubectlError(RuntimeError):
    """Raised when kubectl exits with a non-zero status."""


def kubectl_path() -> str:
    override = os.environ.get("KUBECTL")
    if override:
        return override
    name = "kubectl.exe" if os.name == "nt" else "kubectl"
    local = REPO_ROOT / "tools" / "bin" / name
    if local.exists():
        return str(local)
    return "kubectl"


def run(
    args: list[str],
    stdin: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [kubectl_path(), *args]
    result = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    if check and result.returncode != 0:
        raise KubectlError(
            f"{' '.join(command)} failed ({result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def apply_manifest(manifest: dict[str, Any]) -> str:
    result = run(["apply", "-f", "-"], stdin=json.dumps(manifest))
    return result.stdout.strip()


def active_names(namespace: str, label_selector: str) -> list[str]:
    result = run(
        [
            "get",
            CHAOS_KINDS,
            "-n",
            namespace,
            "-l",
            label_selector,
            "-o",
            "name",
            "--ignore-not-found=true",
        ],
        check=False,
    )
    if result.returncode != 0:
        # No matching CRD or no resources yet is not an error for cleanup.
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def delete_names(names: list[str], namespace: str) -> list[str]:
    deleted: list[str] = []
    for name in names:
        result = run(
            ["delete", name, "-n", namespace, "--ignore-not-found=true"],
            check=False,
        )
        if result.returncode == 0:
            deleted.append(name)
    return deleted


def pod_states(namespace: str) -> list[dict[str, str]]:
    result = run(
        [
            "get",
            "pods",
            "-n",
            namespace,
            "-o",
            "jsonpath={range .items[*]}{.metadata.name}{' '}{.status.phase}{'\\n'}{end}",
        ],
        check=False,
    )
    states: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            states.append({"name": parts[0], "phase": parts[1]})
    return states
