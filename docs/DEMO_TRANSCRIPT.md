# ChaosArena - Technical Demonstration
One-command replay from committed evidence and a real live audit artifact.
Run: python scripts/technical_demo.py   (or --markdown for this transcript)
No mocked gate response and no live cluster mutation during the replay.

## 1. Architecture and why the release gate exists
```text
attacker (allowlisted Chaos Mesh)
    -> defender (Prometheus signals only)
        -> controller (score + hard safety gate)
            -> dashboard / CI decision history
```

- The attacker can only touch namespace shop-test and labelled test services.
- The defender never imports or reads the attacker; it only observes metrics.
- The controller recomputes the score from observed facts and requires cleanup safety, not just a passing number.
- Reason for the gate: a release can look healthy until a controlled fault exposes it.

- **bad config PAYMENT_FAILURE_RATE=1.0:** 65/D/BLOCK
- **after rollback to 0.01:** 100/A/PROMOTE
> The rollback was performed by the experiment script; the verdict came from the gate.

## 2. Controlled fault targeting payment-service
- **attack:** network-latency
- **kind:** NetworkChaos
- **namespace:** shop-test
- **selector.app:** payment-service
- **action / direction:** delay / to
- **latency:** 300ms
- **duration:** 30s
- **cleanup label:** true

- **real manifest name:** chaosarena-network-latency-d9c2639d
- **started -> ended:** 2026-11-20T06:35:52+00:00 -> 2026-11-20T06:36:23+00:00
- **attacker cleanup_ok:** True

- **hard namespace allowlist:** shop-test
- No arbitrary target: every generated fault is checked before kubectl applies it.

## 3. Detection, recovery and cleanup evidence
- **fault:** network-latency on payment-service (release-candidate)
- **detected:** True after 13.3 s
- **detection basis:** seconds since attacker launch until first anomaly observation
- **diagnosis:** latency_spike / order-service / confidence 0.99
- **strongest signal:** order-service_p95_latency z=+403.7
- **remediation requested:** restart on order-service (requested)
- **recovered:** True after 76.2 s
- **final anomaly:** 0.5548 <= threshold 0.7397
- **cleanup:** ok=True, chaos objects left=0
> Recovery is reported separately; the score does not claim fast recovery.

## 4. How the scoring engine reaches PROMOTE or BLOCK
Start at 100. Penalties are explicit; the gate then adds hard safety checks.
- score >= threshold AND cleanup_ok AND 0 chaos objects AND no attacker error -> PROMOTE
- any failed safety check -> BLOCK, even if the numeric score is high

- **committed headline:** 100/A/PROMOTE
- **deductions:** none
- **gate reasons:** score 100 meets threshold 70; attack cleanup succeeded; no chaos objects left behind
- **stored verdict:** PROMOTE (recomputed: PROMOTE)

- **real live audit artifact:** 65/D/BLOCK
- **deductions:** service did not return to a normal score (-25), final anomaly score is still above threshold (-10)
- **gate reasons:** score 65 is below threshold 70; attack cleanup succeeded; no chaos objects left behind
- **stored verdict:** BLOCK (recomputed: BLOCK)

- **recalibrated live artifact:** 70/C/PROMOTE
- **deductions:** fault was never detected (-30)
- **gate reasons:** score 70 meets threshold 70; attack cleanup succeeded; no chaos objects left behind
- **stored verdict:** PROMOTE (recomputed: PROMOTE)

## 5. Real audit artifact: decision recomputation from recorded facts
Artifact: docs/audit/live_battle_2026-11-20.json

$ python -m ci.gate check --evidence docs/audit/live_battle_2026-11-20.json --threshold 70 --expect BLOCK
```text
{
  "evidence": "docs/audit/live_battle_2026-11-20.json",
  "expected": "BLOCK",
  "verdict": "BLOCK",
  "passed": true,
  "score": 65,
  "grade": "D",
  "threshold": 70,
  "deductions": [
    "service did not return to a normal score (-25)",
    "final anomaly score is still above threshold (-10)"
  ],
  "reasons": [
    "score 65 is below threshold 70",
    "attack cleanup succeeded",
    "no chaos objects left behind"
  ],
  "version": "release-candidate",
  "attack": "network-latency",
  "target": "payment-service"
}
GATE PASSED: BLOCK (score 65, threshold 70)
```

- **stored decision:** BLOCK / 65 / D

> Only a temporary copy was edited; the committed artifact is untouched.

$ python -m ci.gate check --evidence <temporary tampered copy> --threshold 70 --expect BLOCK
```text
{
  "evidence": "<temporary tampered copy>",
  "expected": "BLOCK",
  "verdict": "BLOCK",
  "passed": true,
  "score": 65,
  "grade": "D",
  "threshold": 70,
  "deductions": [
    "service did not return to a normal score (-25)",
    "final anomaly score is still above threshold (-10)"
  ],
  "reasons": [
    "score 65 is below threshold 70",
    "attack cleanup succeeded",
    "no chaos objects left behind"
  ],
  "version": "release-candidate",
  "attack": "network-latency",
  "target": "payment-service"
}
GATE PASSED: BLOCK (score 65, threshold 70)
```

## 6. Result
- Architecture and gate rationale shown from code configuration and real bad-release evidence.
- Controlled payment-service fault shown from the generated Chaos Mesh manifest and attacker log.
- Detection, recovery and cleanup read from the committed battle evidence.
- Scoring recomputed live by the real controller code for PROMOTE and BLOCK cases.
- Stored verdict was not trusted; the gate recomputed BLOCK from the recorded battle facts.

TECHNICAL DEMO PASSED
