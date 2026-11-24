"""Exercise all three LLM roles live and record impact without storing keys.

Run after creating a gitignored .env with GROQ_ATTACKER_KEY,
GROQ_DEFENDER_KEY and GROQ_REPORT_KEY. Missing keys fall back to the offline
template backend, so this script is always safe to run.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from attacker.strategist import GroqStrategist, TemplateStrategist
from defender.analyst import GroqAnalyst, TemplateAnalyst
from reporter.env_loader import load_env
from reporter.incident import load_latest
from reporter.report import IncidentReporter
from reporter.role_clients import ROLES, client_for, role_config

OBSERVATION = {
    "score": 65,
    "target": "payment-service",
    "last_action": "network-latency",
    "anomaly_score": 0.72,
    "detected": True,
}
FACTS = {
    "score": 65,
    "top_features": ["payment-service_p95_latency", "order-service_error_rate"],
    "anomaly_score": 0.72,
    "detected": True,
}


def _timed(name: str, call: Callable[[], Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        payload = result.to_dict() if hasattr(result, "to_dict") else {"backend": getattr(result, "backend", "unknown")}
        return {"role": name, "ok": True, "latency_ms": elapsed, "result": payload}
    except Exception as exc:  # noqa: BLE001 - report, never crash the check
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return {
            "role": name,
            "ok": False,
            "latency_ms": elapsed,
            "error": " ".join(str(exc).split())[:300],
        }


def _groq_or_template(role: str) -> tuple[Any, str]:
    try:
        return client_for(role, backend="groq"), "groq"
    except Exception:  # noqa: BLE001 - missing key or config means offline
        return None, "template"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.llm_live_check")
    parser.add_argument("--out", default="ml/deep/llm_live_check.json")
    parser.add_argument("--report-out", default="ml/deep/incident_report_groq.md")
    parser.add_argument("--evidence", default="ml/last_battle.json")
    args = parser.parse_args(argv)

    load_env()
    calls: list[dict[str, Any]] = []

    attacker_client, attacker_backend = _groq_or_template("attacker")
    strategist = (
        GroqStrategist(client=attacker_client)
        if attacker_backend == "groq"
        else TemplateStrategist()
    )
    calls.append(_timed("attacker", lambda: strategist.propose(OBSERVATION)))
    calls.append(_timed("attacker_cached", lambda: strategist.propose(OBSERVATION)))

    defender_client, defender_backend = _groq_or_template("defender")
    analyst = (
        GroqAnalyst(client=defender_client)
        if defender_backend == "groq"
        else TemplateAnalyst()
    )
    calls.append(_timed("defender", lambda: analyst.analyse(FACTS)))

    report_client, report_backend = _groq_or_template("report")

    def make_report() -> Any:
        incident = load_latest(args.evidence)
        rendered = IncidentReporter(report_client).report(incident)
        target = Path(args.report_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered.text, encoding="utf-8")
        return type("ReportResult", (), {
            "backend": rendered.backend,
            "to_dict": lambda self: {
                "backend": rendered.backend,
                "sections": rendered.sections if hasattr(rendered, "sections") else None,
                "chars": len(rendered.text),
                "saved_to": str(target),
            },
        })()

    if report_backend == "groq":
        calls.append(_timed("report", make_report))
    else:
        calls.append({
            "role": "report",
            "ok": True,
            "latency_ms": 0.0,
            "result": {"backend": "template", "skipped": "no GROQ_REPORT_KEY"},
        })

    payload = {
        "version": "v1.2-deep-aiml",
        "key_config": [role_config(role) for role in ROLES],
        "calls": calls,
        "notes": ["Key values are never recorded; only whether each role key is set."],
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
