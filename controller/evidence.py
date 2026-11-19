"""Persist the full evidence bundle for one battle.

Phase 4's decision log records only the decision. The incident reporter needs
the battle facts too, so the controller writes one combined JSON file as well.
"""
from __future__ import annotations

import json
from pathlib import Path

LAST_BATTLE = Path("ml/last_battle.json")


def record_battle(payload: dict, path: Path | str = LAST_BATTLE) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def load_battle(path: Path | str = LAST_BATTLE) -> dict | None:
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))
