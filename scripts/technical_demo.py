"""Short technical demonstration built only from real ChaosArena artifacts.

The replay does not run a cluster battle and does not fake one. It reads the
committed headline evidence and the real live audit artifact, calls the real
scoring/gate code, and shows that a tampered stored decision is still rejected.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.gate import check_bundle, load_bundle
from controller.gate import DEFAULT_THRESHOLD, evaluate_gate
from controller.score import score_battle

HEADLINE = ROOT / "ml" / "last_battle.json"
ATTACK_LOG = ROOT / "ml" / "last_attack.json"
BAD_RELEASE = ROOT / "ml" / "bad_release_experiment.json"
AUDIT_BLOCK = ROOT / "docs" / "audit" / "live_battle_2026-11-20.json"
AUDIT_PROMOTE = ROOT / "docs" / "audit" / "live_battle_recalibrated_2026-11-20.json"

REQUIRED = [HEADLINE, ATTACK_LOG, BAD_RELEASE, AUDIT_BLOCK, AUDIT_PROMOTE]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(module_args: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, "-m", *module_args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(module_args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


class Out:
    def __init__(self, markdown: bool) -> None:
        self.md = markdown

    def title(self, text: str) -> None:
        print(f"# {text}" if self.md else f"\n{'=' * 72}\n{text}\n{'=' * 72}")

    def section(self, number: int, text: str) -> None:
        label = f"{number}. {text}"
        print(f"\n## {label}" if self.md else f"\n--- {label} " + "-" * max(0, 65 - len(label)))

    def line(self, text: str = "") -> None:
        print(text)

    def bullet(self, text: str) -> None:
        print(f"- {text}" if self.md else f"  - {text}")

    def kv(self, key: str, value: object) -> None:
        print(f"- **{key}:** {value}" if self.md else f"  {key:<28} {value}")

    def code(self, text: str, lang: str = "text") -> None:
        print(f"```{lang}\n{text}\n```" if self.md else text)

    def note(self, text: str) -> None:
        print(f"> {text}" if self.md else f"  NOTE: {text}")


def architecture(out: Out) -> None:
    out.section(1, "Architecture and why the release gate exists")
    out.code(
        "attacker (allowlisted Chaos Mesh)\n"
        "    -> defender (Prometheus signals only)\n"
        "        -> controller (score + hard safety gate)\n"
        "            -> dashboard / CI decision history",
    )
    out.line()
    out.bullet("The attacker can only touch namespace shop-test and labelled test services.")
    out.bullet("The defender never imports or reads the attacker; it only observes metrics.")
    out.bullet(
        "The controller recomputes the score from observed facts and requires cleanup "
        "safety, not just a passing number."
    )
    out.bullet(
        "Reason for the gate: a release can look healthy until a controlled fault "
        "exposes it."
    )

    bad = load(BAD_RELEASE)
    bad_decision = bad["bad_release"]["evidence"]["decision"]
    good_decision = bad["rollback"]["evidence"]["decision"]
    out.line()
    out.kv("bad config PAYMENT_FAILURE_RATE=1.0", f"{bad_decision['score']}/{bad_decision['grade']}/{bad_decision['verdict']}")
    out.kv("after rollback to 0.01", f"{good_decision['score']}/{good_decision['grade']}/{good_decision['verdict']}")
    out.note("The rollback was performed by the experiment script; the verdict came from the gate.")


def controlled_fault(out: Out) -> None:
    out.section(2, "Controlled fault targeting payment-service")
    manifest = json.loads(run(["attacker.cli", "show", "network-latency", "--target", "payment-service", "--duration", "30"]))
    spec = manifest["spec"]
    attack_log = load(ATTACK_LOG)
    out.kv("attack", manifest["metadata"]["labels"]["chaosarena.io/attack-name"])
    out.kv("kind", manifest["kind"])
    out.kv("namespace", manifest["metadata"]["namespace"])
    out.kv("selector.app", spec["selector"]["labelSelectors"]["app"])
    out.kv("action / direction", f"{spec['action']} / {spec['direction']}")
    out.kv("latency", spec["delay"]["latency"])
    out.kv("duration", spec["duration"])
    out.kv("cleanup label", manifest["metadata"]["labels"]["chaosarena.io/attack"])
    out.line()
    out.kv("real manifest name", attack_log["manifest"])
    out.kv("started -> ended", f"{attack_log['started_at']} -> {attack_log['ended_at']}")
    out.kv("attacker cleanup_ok", attack_log["cleanup_ok"])

    guard = json.loads(run(["attacker.cli", "guard"]))
    out.line()
    out.kv("hard namespace allowlist", ", ".join(guard["allowed_namespaces"]))
    out.bullet("No arbitrary target: every generated fault is checked before kubectl applies it.")


def evidence(out: Out) -> None:
    out.section(3, "Detection, recovery and cleanup evidence")
    payload = load(HEADLINE)
    battle = payload["battle"]
    diagnosis = battle["diagnosis"]
    action = battle["action_taken"]
    out.kv("fault", f"{battle['attack']} on {battle['target']} ({battle['version']})")
    out.kv("detected", f"{battle['detected']} after {battle['detection_seconds']} s")
    out.kv("detection basis", battle["detection_basis"])
    out.kv("diagnosis", f"{diagnosis['category']} / {diagnosis['service']} / confidence {diagnosis['confidence']}")
    out.kv("strongest signal", diagnosis["evidence"][0])
    out.kv("remediation requested", f"{action['action']} on {action['service']} ({action['status']})")
    out.kv("recovered", f"{battle['recovered']} after {battle['recovery_seconds']} s")
    out.kv("final anomaly", f"{battle['final_score']} <= threshold {battle['defender_threshold']}")
    out.kv("cleanup", f"ok={battle['cleanup_ok']}, chaos objects left={battle['chaos_objects_remaining']}")
    out.note("Recovery is reported separately; the score does not claim fast recovery.")


def recompute(path: Path, threshold: int = DEFAULT_THRESHOLD) -> dict:
    result = load_bundle(path)
    scored = score_battle(result)
    decision = evaluate_gate(result, scored, threshold=threshold)
    return {
        "score": scored.score,
        "grade": scored.grade,
        "deductions": scored.deductions,
        "verdict": decision.verdict,
        "reasons": decision.reasons,
        "stored_verdict": load(path).get("decision", {}).get("verdict"),
    }


def scoring(out: Out) -> dict:
    out.section(4, "How the scoring engine reaches PROMOTE or BLOCK")
    out.line("Start at 100. Penalties are explicit; the gate then adds hard safety checks.")
    out.bullet("score >= threshold AND cleanup_ok AND 0 chaos objects AND no attacker error -> PROMOTE")
    out.bullet("any failed safety check -> BLOCK, even if the numeric score is high")

    cases = [
        ("committed headline", HEADLINE),
        ("real live audit artifact", AUDIT_BLOCK),
        ("recalibrated live artifact", AUDIT_PROMOTE),
    ]
    results: dict[str, dict] = {}
    for label, path in cases:
        value = recompute(path)
        results[label] = value
        detail = ", ".join(value["deductions"]) if value["deductions"] else "none"
        out.line()
        out.kv(label, f"{value['score']}/{value['grade']}/{value['verdict']}")
        out.kv("deductions", detail)
        out.kv("gate reasons", "; ".join(value["reasons"]))
        out.kv("stored verdict", f"{value['stored_verdict']} (recomputed: {value['verdict']})")
    return results


def audit(out: Out) -> str:
    out.section(5, "Real audit artifact: independent recomputation")
    out.line(f"Artifact: {AUDIT_BLOCK.relative_to(ROOT).as_posix()}")
    out.line()
    out.line("$ python -m ci.gate check --evidence docs/audit/live_battle_2026-11-20.json --threshold 70 --expect BLOCK")
    relative_audit = AUDIT_BLOCK.relative_to(ROOT).as_posix()
    first_output = run(
        ["ci.gate", "check", "--evidence", str(AUDIT_BLOCK), "--threshold", "70", "--expect", "BLOCK"]
    ).replace(str(AUDIT_BLOCK), relative_audit).replace(str(AUDIT_BLOCK).replace("\\", "\\\\"), relative_audit)
    out.code(first_output)

    payload = load(AUDIT_BLOCK)
    out.line()
    out.kv("stored decision", f"{payload['decision']['verdict']} / {payload['decision']['score']} / {payload['decision']['grade']}")
    out.line()

    with tempfile.TemporaryDirectory(prefix="chaosarena-demo-") as tmp:
        tampered_path = Path(tmp) / "tampered_battle.json"
        tampered = json.loads(json.dumps(payload))
        tampered["score"] = {"score": 100, "grade": "A", "deductions": []}
        tampered["decision"].update(
            {
                "verdict": "PROMOTE",
                "promote": True,
                "score": 100,
                "grade": "A",
                "reasons": ["score 100 meets threshold 70"],
            }
        )
        tampered_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
        out.note("Only a temporary copy was edited; the committed artifact is untouched.")
        out.line()
        out.line("$ python -m ci.gate check --evidence <temporary tampered copy> --threshold 70 --expect BLOCK")
        output = run(
            [
                "ci.gate",
                "check",
                "--evidence",
                str(tampered_path),
                "--threshold",
                "70",
                "--expect",
                "BLOCK",
            ]
        )
        display_output = (
            output.replace(str(tampered_path), "<temporary tampered copy>")
            .replace(str(tampered_path).replace("\\", "\\\\"), "<temporary tampered copy>")
            .replace(str(AUDIT_BLOCK), AUDIT_BLOCK.relative_to(ROOT).as_posix())
            .replace(str(AUDIT_BLOCK).replace("\\", "\\\\"), AUDIT_BLOCK.relative_to(ROOT).as_posix())
        )
        out.code(display_output)
        tampered_result = check_bundle(tampered_path, 70, "BLOCK")

    return tampered_result["verdict"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", action="store_true", help="emit a Markdown transcript")
    args = parser.parse_args(argv)

    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.exists()]
    if missing:
        print("Missing required real artifacts: " + ", ".join(missing), file=sys.stderr)
        return 2

    out = Out(markdown=args.markdown)
    out.title("ChaosArena - Technical Demonstration")
    out.line("One-command replay from committed evidence and a real live audit artifact.")
    out.line("Run: python scripts/technical_demo.py   (or --markdown for this transcript)")
    out.line("No mocked gate response and no live cluster mutation during the replay.")

    architecture(out)
    controlled_fault(out)
    evidence(out)
    results = scoring(out)
    tampered_verdict = audit(out)

    assert results["committed headline"]["verdict"] == "PROMOTE"
    assert results["real live audit artifact"]["verdict"] == "BLOCK"
    assert results["recalibrated live artifact"]["verdict"] == "PROMOTE"
    assert tampered_verdict == "BLOCK"

    out.section(6, "Result")
    out.bullet("Architecture and gate rationale shown from code configuration and real bad-release evidence.")
    out.bullet("Controlled payment-service fault shown from the generated Chaos Mesh manifest and attacker log.")
    out.bullet("Detection, recovery and cleanup read from the committed battle evidence.")
    out.bullet("Scoring recomputed live by the real controller code for PROMOTE and BLOCK cases.")
    out.bullet("Tampered stored decision ignored; the independent gate still returned BLOCK.")
    out.line()
    out.line("TECHNICAL DEMO PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
