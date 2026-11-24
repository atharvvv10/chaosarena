"""Show the three role-scoped LLM configs without printing any key values."""
from __future__ import annotations

import json

from reporter.role_clients import ROLES, role_config


def main() -> int:
    print(json.dumps({
        "roles": [role_config(role) for role in ROLES],
        "notes": [
            "Live map: attacker=GROQ_ATTACKER_KEY, defender=GEMINI_DEFENDER_KEY, report=GROQ_REPORT_KEY.",
            "GROQ_API_KEY and GEMINI_API_KEY are shared fallbacks per provider.",
            "Default backend stays template (offline); the live check uses the preferred backend.",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
