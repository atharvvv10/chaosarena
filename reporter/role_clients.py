"""Role-scoped LLM clients with a mixed free-tier provider map.

v1.2 uses three isolated keys: Groq for the attacker strategist, Gemini for the
defender analyst, and Groq for the report writer. Each role still has its own
backend/model env vars and an offline template fallback, so CI needs no keys.
"""
from __future__ import annotations

import os
from typing import Literal

from .env_loader import load_env
from .llm import (
    GEMINI_MODEL,
    GROQ_MODEL,
    GeminiLLM,
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

PRIMARY_PROVIDERS: dict[Role, str] = {
    "attacker": "groq",
    "defender": "gemini",
    "report": "groq",
}


def primary_provider(role: Role) -> str:
    """The provider this role uses in the live validation run."""
    return PRIMARY_PROVIDERS[role]


def groq_key_env(role: Role) -> str:
    return f"GROQ_{role.upper()}_KEY"


def gemini_key_env(role: Role) -> str:
    return f"GEMINI_{role.upper()}_KEY"


def key_env(role: Role, provider: str | None = None) -> str:
    """Primary key variable for a role, or an explicitly requested provider."""
    selected = (provider or primary_provider(role)).lower()
    if selected == "groq":
        return groq_key_env(role)
    if selected == "gemini":
        return gemini_key_env(role)
    raise LLMError(f"unknown provider {selected!r}; use groq or gemini")


def preferred_backend(role: Role) -> str:
    """Live backend for a role: explicit env override or the planned provider."""
    return os.getenv(
        f"CHAOSARENA_{role.upper()}_LLM_BACKEND", primary_provider(role)
    ).lower()


def client_for(role: Role, backend: str | None = None) -> LLMClient:
    """Build the LLM client for one role from its own environment variables."""
    prefix = role.upper()
    selected = (backend or os.getenv(f"CHAOSARENA_{prefix}_LLM_BACKEND", "template")).lower()
    model = os.getenv(f"CHAOSARENA_{prefix}_LLM_MODEL")

    if selected == "template":
        return TemplateLLM()
    if selected == "groq":
        return GroqLLM(
            model=model or GROQ_MODEL,
            key_env=groq_key_env(role),
        )
    if selected == "gemini":
        return GeminiLLM(
            model=model or GEMINI_MODEL,
            key_env=gemini_key_env(role),
        )
    if selected == "openai":
        return OpenAICompatibleLLM(
            url=os.getenv(f"CHAOSARENA_{prefix}_LLM_URL", ""),
            model=model or "llama3",
            api_key=os.getenv(f"CHAOSARENA_{prefix}_LLM_KEY"),
        )
    raise LLMError(
        f"unknown LLM backend {selected!r} for {role!r}; "
        "use template, groq, gemini or openai"
    )


def role_config(role: Role) -> dict[str, str]:
    """Describe the active config without revealing any key value."""
    prefix = role.upper()
    return {
        "role": role,
        "backend": os.getenv(f"CHAOSARENA_{prefix}_LLM_BACKEND", "template"),
        "preferred_backend": preferred_backend(role),
        "key_env": key_env(role),
        "key_set": "yes" if os.getenv(key_env(role)) else "no",
        "groq_key_env": groq_key_env(role),
        "groq_key_set": "yes" if os.getenv(groq_key_env(role)) else "no",
        "gemini_key_env": gemini_key_env(role),
        "gemini_key_set": "yes" if os.getenv(gemini_key_env(role)) else "no",
        "shared_key_set": "yes" if (
            os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")
        ) else "no",
        "model_env": f"CHAOSARENA_{prefix}_LLM_MODEL",
    }
