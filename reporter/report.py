"""Generate and validate a structured incident report."""
from __future__ import annotations

from dataclasses import dataclass

from .incident import Incident
from .llm import LLMClient, default_client
from .prompt import build_prompt
from .sections import REQUIRED_SECTIONS


class ReporterError(RuntimeError):
    """Raised when a report is missing required sections."""


@dataclass
class IncidentReport:
    incident: Incident
    text: str
    backend: str

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "version": self.incident.version,
            "verdict": self.incident.verdict,
            "score": self.incident.score,
            "text": self.text,
        }


def missing_sections(text: str) -> list[str]:
    """Accept both `## Heading` and `**Heading**` from real LLM responses."""
    lowered = text.lower()
    return [
        section
        for section in REQUIRED_SECTIONS
        if f"## {section.lower()}" not in lowered
        and f"**{section.lower()}**" not in lowered
    ]


class IncidentReporter:
    """Turn facts into a validated Markdown report using the chosen backend."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or default_client()

    def report(self, incident: Incident) -> IncidentReport:
        text = self.client.complete(build_prompt(incident), incident.as_dict()).strip()
        missing = missing_sections(text)
        if missing:
            raise ReporterError(
                "report is missing required sections: " + ", ".join(missing)
            )
        return IncidentReport(
            incident=incident,
            text=text,
            backend=getattr(self.client, "name", type(self.client).__name__),
        )
