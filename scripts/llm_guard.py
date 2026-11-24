"""Show the three role-scoped LLM configs without printing any key values."""
from __future__ import annotations

import json

from reporter.role_clients import ROLES, role_config


def main() -> int:
    print(json.dumps({
        "roles": [role_config(role) for role in ROLES],
        "notes": [
            "Each role prefers its own GROQ_<ROLE>_KEY.",
            "GROQ_API_KEY is the shared fallback when a role key is absent.",
            "Default backend is template (offline) for every role.",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
