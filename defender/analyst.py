"""LLM defender analyst: explains an anomaly and recommends a remediation.

Uses the defender's *own* Groq key so its traffic is isolated from the attacker
strategist and the report writer. Falls back to a deterministic explanation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from reporter.llm import GroqLLM, LLMError
from reporter.role_clients import client_for


class AnalystError(RuntimeError):
    """Raised when an analyst response cannot be accepted."""


@dataclass(frozen=True)
class Analysis:
    category: str
    confidence: float
    rationale: str
    recommended_action: str
    source: str
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
            "source": self.source,
            "cached": self.cached,
        }


class Analyst(Protocol):
    def analyse(self, facts: Mapping[str, Any]) -> Analysis: ...


class TemplateAnalyst:
    source = "template"

    def analyse(self, facts: Mapping[str, Any]) -> Analysis:
        features = facts.get("top_features") or []
        top = str(features[0]) if features else "unknown signal"
        category = "latency" if "latency" in top else "error-rate" if "error" in top else "traffic"
        return Analysis(
            category=category,
            confidence=0.5,
            rationale=f"Offline heuristic based on {top}.",
            recommended_action="Verify the anomaly with the next metric sample before acting.",
            source=self.source,
        )


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        raise AnalystError("LLM returned no JSON object")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise AnalystError("LLM JSON was not an object")
    return payload


class GroqAnalyst:
    """Role-scoped Groq analyst with caching, retries and safe fallback."""

    source = "groq"

    def __init__(
        self,
        client: Any | None = None,
        fallback: Analyst | None = None,
        cache_size: int = 128,
        max_retries: int = 2,
    ) -> None:
        self.client = client or client_for("defender", backend="groq")
        self.fallback = fallback or TemplateAnalyst()
        self.cache: dict[str, Analysis] = {}
        self.cache_size = cache_size
        self.max_retries = max_retries
        self.last_error: str | None = None

    def _prompt(self, facts: Mapping[str, Any]) -> str:
        return (
            "You are the defender analyst in a private chaos-engineering lab.\n"
            "Explain the anomaly using ONLY these recorded facts. Do not invent numbers.\n"
            "Return ONLY JSON with keys category, confidence, rationale, recommended_action.\n"
            f"Facts: {json.dumps(dict(facts), sort_keys=True, default=str)}\n"
        )

    def analyse(self, facts: Mapping[str, Any]) -> Analysis:
        key = json.dumps(dict(facts), sort_keys=True, default=str)
        if key in self.cache:
            return replace(self.cache[key], cached=True)
        for _ in range(self.max_retries):
            try:
                text = self.client.complete(self._prompt(facts), dict(facts))
                payload = _extract_json(text)
                confidence = float(payload.get("confidence", 0.5))
                if not 0.0 <= confidence <= 1.0:
                    raise AnalystError("confidence must be between 0 and 1")
                result = Analysis(
                    category=str(payload.get("category", "unknown"))[:80],
                    confidence=round(confidence, 4),
                    rationale=str(payload.get("rationale", ""))[:500],
                    recommended_action=str(payload.get("recommended_action", ""))[:300],
                    source=self.source,
                )
                if len(self.cache) >= self.cache_size:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = result
                self.last_error = None
                return result
            except (LLMError, AnalystError, ValueError, TypeError) as exc:
                self.last_error = " ".join(str(exc).split())[:300]
        return self.fallback.analyse(facts)


def default_analyst(backend: str | None = None) -> Analyst:
    client = client_for("defender", backend=backend)
    if isinstance(client, GroqLLM):
        return GroqAnalyst(client=client)
    return TemplateAnalyst()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m defender.analyst")
    parser.add_argument("--backend", choices=["template", "groq", "openai"], default=None)
    parser.add_argument("--facts", default="{}", help="JSON facts object")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        facts = json.loads(args.facts)
    except json.JSONDecodeError as exc:
        print(f"invalid facts JSON: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(default_analyst(args.backend).analyse(facts).to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
