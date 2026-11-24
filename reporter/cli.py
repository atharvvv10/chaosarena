"""Command line: python -m reporter.cli <command>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .incident import load_latest
from .llm import GEMINI_MODEL, GROQ_MODEL, GROQ_URL, GEMINI_URL
from .prompt import build_prompt
from .role_clients import ROLES, client_for, gemini_key_env, groq_key_env, key_env
from .report import IncidentReporter
from .sections import REQUIRED_SECTIONS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m reporter.cli",
        description="Phase 5 LLM incident reporter (offline by default).",
    )
    parser.add_argument("--evidence", default="ml/last_battle.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guard", help="print the reporter's backend and safety rules")

    sub.add_parser("show", help="print the facts that will be reported")

    sub.add_parser("prompt", help="print the exact prompt sent to a real LLM")

    report = sub.add_parser("report", help="write a Markdown incident report")
    report.add_argument(
        "--backend",
        choices=["template", "groq", "gemini", "openai"],
        help="override the default (groq and gemini use their free tiers)",
    )
    report.add_argument("--out", default="ml/incident_report.md")
    return parser


def _client(backend: str | None = None):
    """Build the report role's client (its own Groq key, shared key fallback)."""
    return client_for("report", backend=backend)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "guard":
        print(json.dumps({
            "default_backend": "template (offline)",
            "sections": list(REQUIRED_SECTIONS),
            "evidence_file": args.evidence,
            "network_used_by_default": False,
            "role_keys": {role: key_env(role) for role in ROLES},
            "free_llm_backends": ["groq", "gemini"],
            "groq_endpoint": GROQ_URL,
            "groq_model": GROQ_MODEL,
            "groq_key_required": (
                f"{groq_key_env('report')} (free from console.groq.com/keys; "
                "GROQ_API_KEY is the shared fallback)"
            ),
            "gemini_endpoint": GEMINI_URL.format(model=GEMINI_MODEL),
            "gemini_model": GEMINI_MODEL,
            "gemini_key_required": (
                f"{gemini_key_env('defender')} (free from aistudio.google.com/apikey; "
                "GEMINI_API_KEY is the shared fallback)"
            ),
            "paid_backend": "openai (never used by this project)",
            "rules": ["facts only", "no invented numbers", "validated sections"],
        }, indent=2))
        return 0

    incident = load_latest(args.evidence)

    if args.command == "show":
        print(json.dumps(incident.as_dict(), indent=2))
        return 0

    if args.command == "prompt":
        print(build_prompt(incident))
        return 0

    if args.command == "report":
        reporter = IncidentReporter(_client(args.backend))
        result = reporter.report(incident)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.text, encoding="utf-8")
        print(json.dumps({
            "backend": result.backend,
            "saved_to": str(path),
            "report": result.text,
        }, indent=2))
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
