"""LLM attack strategist: proposes an allowlisted attack plan with reasoning.

The LLM never touches Kubernetes. It only suggests a plan; the hard allowlist
rejects anything outside the seven known attack/target pairs. A deterministic
fallback keeps the CLI usable with no key or no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from reporter.llm import GroqLLM, LLMError
from reporter.role_clients import client_for

from .allowlist import ALLOWED_SERVICES
from .specs import ATTACKS

# The only pairs a proposal may name. Reuse the arena's allowlist rather than
# inventing a second source of truth.
from rl.arena import ACTION_SPACE

ALLOWED_PAIRS: frozenset[tuple[str, str]] = frozenset(
    (action.attack, action.target) for action in ACTION_SPACE
)


class StrategistError(RuntimeError):
    """Raised when an LLM proposal cannot be accepted."""


@dataclass(frozen=True)
class StrategyProposal:
    attack: str
    target: str
    duration: int
    rationale: str
    source: str
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack": self.attack,
            "target": self.target,
            "duration": self.duration,
            "rationale": self.rationale,
            "source": self.source,
            "cached": self.cached,
            "allowed": (self.attack, self.target) in ALLOWED_PAIRS,
        }


class Strategist(Protocol):
    def propose(self, observation: Mapping[str, Any]) -> StrategyProposal: ...


class TemplateStrategist:
    """Offline deterministic strategist; also the LLM failure fallback."""

    source = "template"

    def __init__(self, ranked: Sequence[Mapping[str, Any]] | None = None) -> None:
        self.ranked = list(ranked or [])

    def propose(self, observation: Mapping[str, Any]) -> StrategyProposal:
        for item in self.ranked:
            key = str(item.get("action", ""))
            if "@" not in key:
                continue
            attack, target = key.split("@", 1)
            if (attack, target) in ALLOWED_PAIRS:
                return StrategyProposal(
                    attack=attack,
                    target=target,
                    duration=int(observation.get("duration", 20) or 20),
                    rationale="Selected by the offline deterministic/DQN policy.",
                    source=self.source,
                )
        first = ACTION_SPACE[0]
        return StrategyProposal(
            attack=first.attack,
            target=first.target,
            duration=first.duration,
            rationale="Offline fallback: first allowlisted action.",
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
        raise StrategistError("LLM returned no JSON object")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise StrategistError("LLM JSON was not an object")
    return payload


def _validate(payload: dict[str, Any], source: str) -> StrategyProposal:
    attack = str(payload.get("attack", "")).strip()
    target = str(payload.get("target", "")).strip()
    if attack not in ATTACKS:
        raise StrategistError(f"attack {attack!r} is not in the catalogue")
    if target not in ALLOWED_SERVICES:
        raise StrategistError(f"target {target!r} is outside the hard allowlist")
    if (attack, target) not in ALLOWED_PAIRS:
        raise StrategistError(f"pair {attack}@{target} is not an approved action")
    try:
        duration = int(payload.get("duration", 20))
    except (TypeError, ValueError) as exc:
        raise StrategistError("duration must be an integer") from exc
    if not 1 <= duration <= 300:
        raise StrategistError("duration must be between 1 and 300 seconds")
    return StrategyProposal(
        attack=attack,
        target=target,
        duration=duration,
        rationale=str(payload.get("rationale", ""))[:500],
        source=source,
    )


class GroqStrategist:
    """Role-scoped Groq strategist with caching, retries and a safe fallback."""

    source = "groq"

    def __init__(
        self,
        client: Any | None = None,
        fallback: Strategist | None = None,
        cache_size: int = 128,
        max_retries: int = 2,
    ) -> None:
        self.client = client or client_for("attacker", backend="groq")
        self.fallback = fallback or TemplateStrategist()
        self.cache: dict[str, StrategyProposal] = {}
        self.cache_size = cache_size
        self.max_retries = max_retries
        self.last_error: str | None = None

    @staticmethod
    def _cache_key(observation: Mapping[str, Any]) -> str:
        return json.dumps(observation, sort_keys=True, default=str)

    def _prompt(self, observation: Mapping[str, Any]) -> str:
        pairs = ", ".join(sorted(f"{a}@{t}" for a, t in ALLOWED_PAIRS))
        return (
            "You are the attacker strategist in a private chaos-engineering lab.\n"
            f"Choose exactly one approved pair from: {pairs}.\n"
            "Return ONLY a JSON object with keys attack, target, duration, rationale.\n"
            f"Observation: {json.dumps(observation, sort_keys=True, default=str)}\n"
        )

    def propose(self, observation: Mapping[str, Any]) -> StrategyProposal:
        key = self._cache_key(observation)
        if key in self.cache:
            return replace(self.cache[key], cached=True)
        for attempt in range(self.max_retries):
            try:
                text = self.client.complete(self._prompt(observation), dict(observation))
                proposal = _validate(_extract_json(text), self.source)
                if len(self.cache) >= self.cache_size:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = proposal
                self.last_error = None
                return proposal
            except (LLMError, StrategistError, ValueError, TypeError) as exc:
                self.last_error = " ".join(str(exc).split())[:300]
        return self.fallback.propose(observation)


def default_strategist(
    backend: str | None = None,
    ranked: Sequence[Mapping[str, Any]] | None = None,
) -> Strategist:
    fallback = TemplateStrategist(ranked)
    client = client_for("attacker", backend=backend)
    if isinstance(client, GroqLLM):
        return GroqStrategist(client=client, fallback=fallback)
    return fallback


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m attacker.strategist")
    parser.add_argument("--backend", choices=["template", "groq", "openai"], default=None)
    parser.add_argument("--observation", default="{}", help="JSON observation object")
    parser.add_argument("--ranked", default=None, help="JSON file of DQN-ranked actions")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        observation = json.loads(args.observation)
    except json.JSONDecodeError as exc:
        print(f"invalid observation JSON: {exc}", file=sys.stderr)
        return 2
    ranked = None
    if args.ranked:
        ranked = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
    proposal = default_strategist(args.backend, ranked).propose(observation)
    print(json.dumps(proposal.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
