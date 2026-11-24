"""Two interchangeable report backends: offline template or a real chat LLM.

The default is the offline template. Nothing is sent over the network unless
CHAOSARENA_LLM_BACKEND=openai is set explicitly, so the demo works anywhere.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Raised when a report backend cannot produce an answer."""


class LLMClient(Protocol):
    def complete(self, prompt: str, facts: dict[str, Any]) -> str:
        """Return a Markdown incident report for the given facts."""


def _text(value: Any, default: str = "not recorded") -> str:
    if value is None or value == "" or value == []:
        return default
    return str(value)


def _bullet_list(items: Any, indent: str = "") -> str:
    if not items:
        return f"{indent}- None recorded."
    return "\n".join(f"{indent}- {item}" for item in items)


class TemplateLLM:
    """Deterministic, offline reporter. Always available, never calls a network."""

    name = "template"

    def complete(self, prompt: str, facts: dict[str, Any]) -> str:  # noqa: ARG002
        diagnosis = facts.get("diagnosis") or {}
        action = facts.get("action_taken") or {}
        seconds = facts.get("detection_seconds")
        detected = "yes" if facts.get("detected") else "no"
        recovered = "yes" if facts.get("recovered") else "no"
        cleanup = "succeeded" if facts.get("cleanup_ok") else "failed"

        evidence = diagnosis.get("evidence") or []
        if action:
            action_line = (
                f"- `{action.get('action', 'unknown')}` on "
                f"`{action.get('service', 'unknown')}` in "
                f"`{action.get('namespace', 'shop-test')}`"
            )
            when = action.get("timestamp")
            if when:
                action_line += f" at {when}"
        else:
            action_line = "- No remediation action was taken."

        follow_ups: list[str] = []
        deductions = [str(item) for item in (facts.get("deductions") or [])]
        if any("never detected" in item for item in deductions):
            follow_ups.append("Add a detector for this fault family before the next release.")
        if any("longer than 20" in item for item in deductions):
            follow_ups.append("Shorten the metric window or add a faster signal for detection.")
        if any("did not return" in item or "above threshold" in item for item in deductions):
            follow_ups.append("Investigate why the service did not return to baseline quickly.")
        if any("cleanup" in item or "left behind" in item for item in deductions):
            follow_ups.append("Review the chaos cleanup path before running the next battle.")
        if not follow_ups:
            follow_ups.append("Keep the current baseline and repeat this battle in the next release.")

        return "\n".join(
            [
                f"# Incident Report - {_text(facts.get('version'), 'candidate')}",
                "",
                "1. Summary",
                (
                    f"A `{_text(facts.get('attack'))}` fault was injected into "
                    f"`{_text(facts.get('target'))}` in `shop-test` for release candidate "
                    f"`{_text(facts.get('version'), 'candidate')}`. "
                    f"Resilience score: {_text(facts.get('score'), 0)}/100 "
                    f"(grade {_text(facts.get('grade'))}). "
                    f"Gate verdict: {_text(facts.get('verdict'))}."
                ),
                "",
                "2. Timeline",
                f"- Evaluated at: {_text(facts.get('evaluated_at'))}",
                f"- Fault detected: {detected}"
                + (f" after {seconds:.1f} seconds" if seconds is not None else ""),
                f"- Recovery observed: {recovered}"
                + (
                    f" after {facts.get('recovery_seconds'):.1f} seconds"
                    if isinstance(facts.get("recovery_seconds"), (int, float))
                    else ""
                ),
                f"- Chaos cleanup: {cleanup}",
                f"- Chaos objects remaining: {_text(facts.get('chaos_objects_remaining'), 0)}",
                "",
                "3. Root cause",
                f"- Category: {_text(diagnosis.get('category'))}",
                f"- Service: {_text(diagnosis.get('service'))}",
                f"- Confidence: {_text(diagnosis.get('confidence'))}",
                "- Evidence:",
                _bullet_list(evidence, indent="  "),
                "",
                "4. Actions taken",
                action_line,
                "",
                "5. Outcome",
                f"- Returned to normal: {recovered}",
                f"- Final anomaly score: {_text(facts.get('final_score'))} (threshold {_text(facts.get('defender_threshold'))})",
                "- Gate reasons:",
                _bullet_list(facts.get("reasons"), indent="  "),
                "- Score deductions:",
                _bullet_list(deductions, indent="  "),
                "",
                "6. Follow-ups",
                _bullet_list(follow_ups),
                "",
            ]
        )


class OpenAICompatibleLLM:
    """Calls any OpenAI-compatible /chat/completions endpoint via urllib.

    Configure with:
      CHAOSARENA_LLM_URL   full endpoint, e.g. http://localhost:11434/v1/chat/completions
      CHAOSARENA_LLM_MODEL model name, default llama3
      CHAOSARENA_LLM_KEY   optional bearer token
    """

    name = "openai"

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.url = url or os.environ.get("CHAOSARENA_LLM_URL", "")
        self.model = model or os.environ.get("CHAOSARENA_LLM_MODEL", "llama3")
        self.api_key = api_key if api_key is not None else os.environ.get("CHAOSARENA_LLM_KEY")
        self.timeout = timeout
        if not self.url:
            raise LLMError(
                "CHAOSARENA_LLM_URL is not set; set it to an OpenAI-compatible "
                "/v1/chat/completions endpoint"
            )

    def complete(self, prompt: str, facts: dict[str, Any]) -> str:  # noqa: ARG002
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "chaosarena/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - defensive
                pass
            raise LLMError(
                f"LLM request failed: {exc}; response: {detail[:500]}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface one clear error
            raise LLMError(f"LLM request failed: {exc}") from exc


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
# New projects should use the current Flash-Lite model; override with
# CHAOSARENA_REPORT_GEMINI_MODEL if Google changes the recommended model.
GEMINI_MODEL = "gemini-3.5-flash-lite"


class GroqLLM(OpenAICompatibleLLM):
    """Groq's free tier through the same OpenAI-compatible interface.

    Free key: https://console.groq.com/keys  (no card needed for the free plan)
    Default model `openai/gpt-oss-20b` is on the free plan; check current
    limits at https://console.groq.com/docs/rate-limits.
    """

    name = "groq"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        url: str | None = None,
        timeout: int = 120,
        key_env: str = "GROQ_API_KEY",
    ) -> None:
        # Each role can own a distinct key so one role's traffic cannot exhaust
        # another role's quota. GROQ_API_KEY remains the shared fallback.
        key = (
            api_key
            if api_key is not None
            else os.environ.get(key_env) or os.environ.get("GROQ_API_KEY")
        )
        if not key:
            raise LLMError(
                f"{key_env} is not set; create a free key at https://console.groq.com/keys"
            )
        super().__init__(
            url=url or os.environ.get("GROQ_API_URL", GROQ_URL),
            model=model or os.environ.get("GROQ_MODEL", GROQ_MODEL),
            api_key=key,
            timeout=timeout,
        )


class GeminiLLM:
    """Google Gemini via the free generateContent REST endpoint.

    Used only for the report role in v1.2: batch prose is not latency-critical.
    No extra dependency is needed; this uses urllib like the other backends.
    """

    name = "gemini"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        url: str | None = None,
        timeout: int = 120,
        key_env: str = "GEMINI_API_KEY",
    ) -> None:
        key = (
            api_key
            if api_key is not None
            else os.environ.get(key_env) or os.environ.get("GEMINI_API_KEY")
        )
        if not key:
            raise LLMError(
                f"{key_env} is not set; create a free key at https://aistudio.google.com/apikey"
            )
        self.model = model or os.environ.get("GEMINI_MODEL", GEMINI_MODEL)
        endpoint = url or os.environ.get("GEMINI_URL", GEMINI_URL)
        self.url = endpoint.format(model=self.model) if "{model}" in endpoint else endpoint
        self.api_key = key
        self.timeout = timeout

    def complete(self, prompt: str, facts: dict[str, Any]) -> str:  # noqa: ARG002
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
            "User-Agent": "chaosarena/1.2",
        }
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            candidates = payload.get("candidates") or []
            if not candidates:
                feedback = payload.get("promptFeedback") or {}
                raise LLMError(f"Gemini returned no content; feedback: {feedback}")
            parts = ((candidates[0].get("content") or {}).get("parts") or [])
            text = "".join(str(part.get("text", "")) for part in parts).strip()
            if not text:
                raise LLMError("Gemini returned an empty response")
            return text
        except LLMError:
            raise
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - defensive
                pass
            raise LLMError(
                f"Gemini request failed: {exc}; response: {detail[:500]}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surface one clear error
            raise LLMError(f"Gemini request failed: {exc}") from exc


def default_client() -> LLMClient:
    """Pick the backend from the environment. Offline is the default."""
    backend = os.environ.get("CHAOSARENA_LLM_BACKEND", "template").lower()
    if backend == "openai":
        return OpenAICompatibleLLM()
    if backend == "groq":
        return GroqLLM()
    if backend == "gemini":
        return GeminiLLM()
    if backend == "template":
        return TemplateLLM()
    raise LLMError(
        f"unknown CHAOSARENA_LLM_BACKEND {backend!r}; "
        "use template, groq, gemini or openai"
    )
