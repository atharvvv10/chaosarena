"""Run one real Kind/Chaos Mesh battle with v1.2 AIML advisory roles.

Everything is written under ml/deep/live/ by default. The frozen v1.1 evidence
files ml/last_battle.json and ml/gate_decisions.jsonl are never touched.

The hard allowlist and classical defender still own the real control loop. The
DQN, Groq strategist, Gemini analyst and Groq reporter are advisory/Reporting
only, exactly as in the v1.2 architecture.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from attacker.strategist import GroqStrategist, TemplateStrategist
from controller.battle import REPO_ROOT, BattleRunner
from controller.evidence import record_battle
from controller.gate import DEFAULT_THRESHOLD, evaluate_gate, record_decision
from controller.score import score_battle
from defender.analyst import LLMAnalyst, TemplateAnalyst
from reporter.incident import Incident
from reporter.llm import TemplateLLM
from reporter.report import IncidentReporter
from reporter.role_clients import client_for, preferred_backend
from rl.dqn_agent import DQNAgent
from rl.features import encode


def _timed(name: str, call):
    started = time.perf_counter()
    try:
        result = call()
        return {"role": name, "ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "result": result}
    except Exception as exc:  # noqa: BLE001 - advisory failures must not break the gate
        return {
            "role": name,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": " ".join(str(exc).split())[:300],
        }


def _run_module(*args: str) -> None:
    """Run a repo CLI from the repo root; failures stay out of the evidence."""
    result = subprocess.run(
        [sys.executable, "-m", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        detail = " ".join((result.stderr or result.stdout).split())[:300]
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")


def _prepare_defender(data: Path, model: Path, samples: int, interval: float) -> dict[str, Any]:
    """Collect and train an isolated baseline; never touch ml/ v1.1 artifacts."""
    data.parent.mkdir(parents=True, exist_ok=True)
    if not data.exists():
        _run_module(
            "defender.cli", "baseline",
            "--samples", str(samples),
            "--interval", str(interval),
            "--window", "30s",
            "--out", str(data),
        )
    if not model.exists():
        _run_module("defender.cli", "train", "--data", str(data), "--out", str(model))
    return {"baseline": str(data), "model": str(model), "isolated": True}


def _post_analysis(payload: dict[str, Any], out: Path) -> dict[str, Any]:
    """Ask Gemini to explain the *real* recorded battle facts."""
    battle = payload["battle"]
    score = payload["score"]
    decision = payload["decision"]
    facts = {
        "attack": battle.get("attack"),
        "target": battle.get("target"),
        "version": battle.get("version"),
        "detected": battle.get("detected"),
        "detection_seconds": battle.get("detection_seconds"),
        "recovery_seconds": battle.get("recovery_seconds"),
        "cleanup_ok": battle.get("cleanup_ok"),
        "final_score": battle.get("final_score"),
        "threshold": battle.get("defender_threshold"),
        "score": score.get("score"),
        "verdict": decision.get("verdict"),
    }
    try:
        analyst = LLMAnalyst(client=client_for("defender", backend=preferred_backend("defender")))
        call = _timed("defender_post_analysis", lambda: analyst.analyse(facts).to_dict())
        if analyst.last_error:
            call["last_error"] = analyst.last_error
    except Exception:  # noqa: BLE001 - advisory path is optional
        call = _timed(
            "defender_post_analysis",
            lambda: TemplateAnalyst().analyse(facts).to_dict(),
        )
    (out / "defender_analysis.json").write_text(
        json.dumps(call, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return call


def _advisories(attack: str, target: str, duration: int) -> dict[str, Any]:
    observation = {
        "attack": attack,
        "target": target,
        "duration": duration,
        "version": "v1.2-deep-aiml",
        "mode": "live-lab-advisory",
    }

    try:
        strategist = GroqStrategist(client=client_for("attacker", backend=preferred_backend("attacker")))
        proposal_call = _timed("attacker_strategist", lambda: strategist.propose(observation).to_dict())
        if strategist.last_error:
            proposal_call["last_error"] = strategist.last_error
    except Exception:  # noqa: BLE001 - missing key means offline template
        proposal_call = _timed(
            "attacker_strategist",
            lambda: TemplateStrategist().propose(observation).to_dict(),
        )

    facts = {
        "attack": attack,
        "target": target,
        "duration": duration,
        "version": "v1.2-deep-aiml",
        "stage": "preflight",
    }
    try:
        analyst = LLMAnalyst(client=client_for("defender", backend=preferred_backend("defender")))
        # The real facts are not known until after the battle; a preflight note
        # still proves the Gemini analyst path is configured and reachable.
        analyst_call = _timed("defender_analyst", lambda: analyst.analyse(facts).to_dict())
    except Exception:  # noqa: BLE001 - missing key means offline template
        analyst_call = _timed(
            "defender_analyst",
            lambda: TemplateAnalyst().analyse(facts).to_dict(),
        )

    try:
        agent = DQNAgent.load("ml/deep/dqn.pt")
        agent.epsilon = 0.0
        dqn_call = _timed("dqn_attacker", lambda: agent.ranked(encode(None, None, 0, 0.0)))
    except Exception as exc:  # noqa: BLE001 - checkpoint must exist, but fail soft
        dqn_call = {"role": "dqn_attacker", "ok": False, "error": str(exc)[:300]}

    return {
        "note": "Advisory only; the CLI allowlist and classical detector own the real loop.",
        "calls": [proposal_call, analyst_call, dqn_call],
    }


def _write_report(payload: dict, target: Path) -> dict[str, Any]:
    incident = Incident.from_bundle(payload)
    try:
        client = client_for("report", backend=preferred_backend("report"))
        report = IncidentReporter(client).report(incident)
    except Exception:  # noqa: BLE001 - deterministic section-valid report fallback
        report = IncidentReporter(TemplateLLM()).report(incident)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.text, encoding="utf-8")
    return {"backend": report.backend, "chars": len(report.text), "saved_to": str(target)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.live_deep_battle")
    parser.add_argument("--attack", default="network-latency")
    parser.add_argument("--target", default="payment-service")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--settle", type=int, default=45)
    parser.add_argument("--version", default="v1.2-deep-aiml")
    parser.add_argument("--out", default="ml/deep/live")
    parser.add_argument("--defender-model", default="ml/deep/live/defender_model.joblib")
    parser.add_argument("--defender-data", default="ml/deep/live/baseline.csv")
    parser.add_argument("--baseline-samples", type=int, default=30)
    parser.add_argument("--baseline-interval", type=float, default=5.0)
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Keep the frozen v1.1 action log untouched; subprocesses inherit this.
    os.environ["CHAOSARENA_ACTION_LOG"] = str(out / "defender_actions.jsonl")

    defender_info = _prepare_defender(
        Path(args.defender_data),
        Path(args.defender_model),
        args.baseline_samples,
        args.baseline_interval,
    )
    advisories = _advisories(args.attack, args.target, args.duration)
    (out / "advisories.json").write_text(
        json.dumps(advisories, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    runner = BattleRunner(
        settle_seconds=args.settle,
        log_path=out / "last_attack.json",
        defender_model=args.defender_model,
        defender_data=args.defender_data,
    )
    result = runner.run(
        attack=args.attack,
        target=args.target,
        duration=args.duration,
        version=args.version,
    )
    scored = score_battle(result)
    decision = evaluate_gate(result, scored, threshold=args.threshold)
    payload = {
        "battle": result.as_dict(),
        "score": scored.as_dict(),
        "decision": decision.as_dict(),
    }

    battle_path = record_battle(payload, out / "last_battle.json")
    decision_path = record_decision(decision, out / "gate_decisions.jsonl")
    report_info = _write_report(payload, out / "incident_report.md")
    analysis = _post_analysis(payload, out)

    summary = {
        "version": args.version,
        "defender": defender_info,
        "out": str(out),
        "verdict": decision.verdict,
        "score": decision.score,
        "attack": args.attack,
        "target": args.target,
        "detected": result.detected,
        "detection_seconds": result.detection_seconds,
        "recovery_seconds": result.recovery_seconds,
        "cleanup_ok": result.cleanup_ok,
        "chaos_objects_remaining": result.chaos_objects_remaining,
        "battle_file": str(battle_path),
        "decision_file": str(decision_path),
        "report": report_info,
        "defender_analysis": analysis,
        "advisories": advisories,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if decision.promote else 1


if __name__ == "__main__":
    raise SystemExit(main())
