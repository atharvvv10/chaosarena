# Phase 4 — Arena Controller, Resilience Score and release gate

## What this phase adds

A controller that runs a complete **attack → defend → recover** battle, turns the
observations into a 0–100 Resilience Score, and decides whether a version may be
promoted. The decision is written to an audit log and exposed through a small
HTTP API for CI to call later.

The controller drives the attacker and defender **only through their public
CLIs**. It never imports their modules, so it cannot bypass their allowlists.

## Files

| Path | Purpose |
|---|---|
| `controller/score.py` | 0–100 score with named deductions, grade and detection/recovery timing |
| `controller/gate.py` | Promotion decision + append-only decision log |
| `controller/battle.py` | Runs one battle by calling `attacker.cli` and `defender.cli` |
| `controller/api.py` | FastAPI: `/health`, `POST /gate/evaluate`, `/gate/last` |
| `controller/cli.py` | `python -m controller.cli ...` commands |
| `tests/test_phase4.py` | 12 tests |
| `Makefile` | `battle`, `gate`, `gate-api` |
| `docs/phase4.md` | This file |

## How the score works

Start at 100 and subtract:

| Observation | Penalty |
|---|---|
| Fault never detected | −30 |
| Detection took more than 20 seconds | −15 |
| Service did not return to a normal score | −25 |
| Attack cleanup failed | −20 |
| Chaos objects left behind | −20 |
| Final anomaly score still above threshold | −10 |
| Attacker reported an error | −10 |

Grades: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 50, F below 50.

## How the gate decides

Promotion requires **all** of these:

1. score ≥ threshold (default 70),
2. cleanup succeeded,
3. zero chaos objects left,
4. no attacker error.

A high score cannot hide unsafe cleanup. A low score cannot be rescued by
cleanup. Every decision is appended to `ml/gate_decisions.jsonl`.

## Exact commands

```powershell
cd D:\Projects\1\chaosarena

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m controller.cli guard

# Full battle + gate decision
.\.venv\Scripts\python.exe -m controller.cli evaluate `
  --attack network-latency --target payment-service `
  --duration 30 --settle 45 --threshold 70 --version v1.0.1

# Show the last decision
.\.venv\Scripts\python.exe -m controller.cli last

# Same thing through the API
.\.venv\Scripts\python.exe -m uvicorn controller.api:app --host 127.0.0.1 --port 8080
# In another terminal:
#   Invoke-RestMethod http://127.0.0.1:8080/health
#   Invoke-RestMethod http://127.0.0.1:8080/gate/last
```

## Results actually measured on this laptop

- **120 tests pass** across all nine phases after the final evidence checks.
- First `network-latency` battle: detected on the first poll (0.0 s recorded), diagnosed `latency_spike`
  on `order-service`, restarted it, but the final Prometheus sample was still
  inside the 30-second attack window → score **65**, verdict **BLOCK**.
  This was a measurement artefact, not a rejected bad release; it is fixed by
  the bounded settle period below.
- Added a bounded settle period (up to 45 s, polling every 5 s). Second battle:
  detected at 13.9 s, final score **0.598** vs threshold **0.740** → score
  **100**, grade **A**, verdict **PROMOTE** for `v1.0.1`.
- A short `pod-kill` battle through `POST /gate/evaluate` returned score **70**,
  verdict **PROMOTE** — quick self-healing is allowed, but it costs points
  because the Defender never saw an anomaly.
- The controller now records `detection_seconds` and `recovery_seconds` in every
  `BattleResult`. The committed headline battle (`ml/last_battle.json`) was
  detected in **0.0 s (first poll)**, recovered in **57.4 s**, diagnosed `latency_spike` on
  `order-service`, restarted it, and scored **100 / A / PROMOTE** with zero
  deductions and zero chaos objects left.
- API `/health` and `/gate/last` verified live; decision log contains both
  BLOCK and PROMOTE entries.

## Common errors and fixes

| Error / surprise | Cause | Fix |
|---|---|---|
| Gate blocks right after cleanup | `[30s]` Prometheus window still contains the attack | Use `--settle 45`; the controller polls until normal |
| `unknown attack ...` | Name outside the seven known attacks | Use one from `controller.cli guard` |
| `no JSON` from a CLI | kubectl/kubeconfig or model missing | Run the affected CLI directly to see the real error |
| `evaluate` exits with code 1 | The verdict was `BLOCK` | Check `score.deductions`; this is the gate working |

## Why the gate is separate from the Defender

The Defender is allowed to repair, but it is not allowed to decide releases.
The Controller is allowed to decide releases, but it is not allowed to inject
faults directly — it must ask the allowlisted attacker CLI. That separation is
what makes the result trustworthy enough to present.
