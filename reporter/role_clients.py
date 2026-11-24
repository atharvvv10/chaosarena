"""Role-scoped LLM clients: attacker, defender and report get separate keys.

Each role has its own backend, model and Groq key environment variables, so one
role's traffic cannot exhaust another role's quota. A shared ``GROQ_API_KEY``
still works as a fallback for simple setups.
"""
from __future__ import annotations

import os
from typing import Literal

from .env_loader import load_env
from .llm import (
    GROQ_MODEL,
    LLMClient,
    LLMError,
    OpenAICompatibleLLM,
    TemplateLLM,
    GroqLLM,
)

# Local .env is gitignored; real env vars take precedence.
load_env()

Role = Literal["attacker", "defender", "report"]
ROLES: tuple[Role, ...] = ("attacker", "defender", "report")


def key_env(role: Role) -> str:
    return f"GROQ_{role.upper()}_KEY"


def client_for(role: Role, backend: str | None = None) -> LLMClient:
    """Build the LLM client for one role from its own environment variables."""
    prefix = role.upper()
    selected = (backend or os.getenv(f"CHAOSARENA_{prefix}_LLM_BACKEND", "template")).lower()

    if selected == "template":
        return TemplateLLM()
    if selected == "groq":
        return GroqLLM(
            model=os.getenv(f"CHAOSARENA_{prefix}_LLM_MODEL") or GROQ_MODEL,
            key_env=key_env(role),
        )
    if selected == "openai":
        return OpenAICompatibleLLM(
            url=os.getenv(f"CHAOSARENA_{prefix}_LLM_URL", ""),
            model=os.getenv(f"CHAOSARENA_{prefix}_LLM_MODEL", "llama3"),
            api_key=os.getenv(f"CHAOSARENA_{prefix}_LLM_KEY"),
        )
    raise LLMError(
        f"unknown LLM backend {selected!r} for {role!r}; use template, groq or openai"
    )


def role_config(role: Role) -> dict[str, str]:
    """Describe the active config without revealing any key value."""
    prefix = role.upper()
    return {
        "role": role,
        "backend": os.getenv(f"CHAOSARENA_{prefix}_LLM_BACKEND", "template"),
        "key_env": key_env(role),
        "key_set": "yes" if os.getenv(key_env(role)) else "no",
        "shared_key_set": "yes" if os.getenv("GROQ_API_KEY") else "no",
        "model_env": f"CHAOSARENA_{prefix}_LLM_MODEL",
    }
