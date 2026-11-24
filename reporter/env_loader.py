"""Load a local gitignored .env file into os.environ without overriding values.

This keeps keys out of source control and out of chat. Real environment
variables always win over the file, so CI and shells stay in control.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path(".env")


def load_env(path: Path | str = DEFAULT_ENV_FILE) -> int:
    """Load KEY=VALUE lines; return the number of variables loaded."""
    target = Path(path)
    if not target.is_file():
        return 0
    loaded = 0
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or key in os.environ:
            continue
        os.environ[key] = value
        loaded += 1
    return loaded
