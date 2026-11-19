"""The prompt sent to a real LLM, built only from recorded facts."""
from __future__ import annotations

import json

from .incident import Incident
from .sections import REQUIRED_SECTIONS


def build_prompt(incident: Incident) -> str:
    section_list = "\n".join(
        f"{index}. ## {name}" for index, name in enumerate(REQUIRED_SECTIONS, 1)
    )
    return "\n".join(
        [
            "You are a site reliability engineer writing an incident report.",
            "Use ONLY the facts below. Do not invent numbers, services or timestamps.",
            "Write concise Markdown with exactly these six level-2 headings, in this order:",
            section_list,
            "",
            "FACTS (JSON):",
            json.dumps(incident.as_dict(), indent=2),
        ]
    )
