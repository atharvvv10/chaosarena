# Testing Guide

## One command

```powershell
cd D:\Projects\1\chaosarena
make verify
```

This runs `python scripts/verify_all.py`: every pytest suite, all five safety
guards (`ci.gate`, `controller.cli`, `attacker.cli`, `defender.cli`, `rl.cli`),
the CI gate fixture checks, and the React production build. It needs no cluster,
no internet and no secret. The current suite is **179 tests**.

To run it without `make`:

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

## Individual suites

| Command | Checks |
| --- | --- |
| `pytest -q tests/test_phase1.py` | Services, shared observability, local smoke path |
| `pytest -q tests/test_phase2.py` | Seven attacks, allowlist, manifest validation, cleanup |
| `pytest -q tests/test_phase3.py` | Defender isolation, features, model, bounded actions |
| `pytest -q tests/test_phase4.py` | Battle, score, gate, API, CLI-only boundaries |
| `pytest -q tests/test_phase5.py` | Offline/Groq reporters and six-section report |
| `pytest -q tests/test_phase6.py` | Free workflow YAML, CI gate decision recomputation |
| `pytest -q tests/test_phase7.py` | Dashboard API, CORS, free packages, panels |
| `pytest -q tests/test_phase8.py` | RL safety, Q-learning, sim/real paths |
| `pytest -q tests/test_phase9.py` | Final docs, RL policy API, polish, no-paid scan |
| `pytest -q tests/test_ai_panel.py` | AI reasoning endpoint, AI battle checkbox, fresh runtime notes, no-key/no-torch fallback, v1.1 media guards |

## Cluster-dependent checks (manual)

These are intentionally not in CI because CI has no cluster:

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
.\.venv\Scripts\python.exe -m attacker.cli status
.\.venv\Scripts\python.exe -m attacker.cli guard
.\.venv\Scripts\python.exe -m defender.cli guard
```

Expected: `chaos_objects: []`, all pods `Running`.

A live battle also needs Prometheus on `localhost:9090`. Start it in its own
terminal before running the defender:

```powershell
kubectl -n monitoring port-forward svc/prometheus 9090:9090
.\.venv\Scripts\python.exe -m defender.cli detect   # must be below the printed threshold
```

If the pre-attack score is already anomalous, the committed 40-sample baseline
does not describe current traffic; recalibrate with the documented
`defender.cli baseline --samples 40 --interval 3 --window 30s` and
`defender.cli train`, then restore the committed files when returning to the
published demo. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) and
[DEMO_AUDIT.md](DEMO_AUDIT.md).

To run one real gated battle:

```powershell
.\.venv\Scripts\python.exe -m controller.cli evaluate --attack network-latency --target payment-service --duration 30 --threshold 70 --settle 45 --version release-candidate
```

The sustained latency fault is sized to stay visible across a Prometheus window,
but detection is not guaranteed: a 10-second partition can heal inside that
window, and a stale baseline can either hide the fault or make normal traffic
look anomalous. These are honest results, explained in
[RESULTS.md](RESULTS.md#headline-gated-battle) and
[DEMO_AUDIT.md](DEMO_AUDIT.md).

Or let the RL attacker choose:

```powershell
.\.venv\Scripts\python.exe -m rl.cli real --episodes 1 --duration 10 --settle 20 --threshold 0
```

Always confirm cleanup afterwards with `attacker.cli status`.

## Offline benchmarks (no cluster)

These regenerate the two committed evidence files used in the README results
table. They are reproducible and cluster-free:

```powershell
.\.venv\Scripts\python.exe -m rl.cli benchmark        # writes ml/rl_benchmark.json
.\.venv\Scripts\python.exe -m defender.cli benchmark  # writes ml/defender_benchmark.json
```

The first shows the learned attacker does more damage than random; the second
compares a rule-based detector, a plain Isolation Forest and the shipped Defender
on the recorded baseline plus seeded fault signatures. Both are offline
benchmarks, not live battles.

## v1.1 experimental validation (needs lab)

The repeated-trial harness is separate from the offline benchmarks. It runs real
Chaos Mesh faults against the isolated `shop-test` namespace and writes only to
`ml/experimental_validation/`. Full methodology and results are in
[EXPERIMENTAL_VALIDATION.md](EXPERIMENTAL_VALIDATION.md).

```powershell
make experimental-validation  # 10 paired trials; default cpu-stress@order-service
make experimental-holdout     # 30 non-overlapping normal windows, frozen model
make experimental-summary     # recompute statistics from the recorded JSONL files
```

Prerequisites are the same as a live battle: Docker Desktop, the `kind-chaosarena`
cluster, Chaos Mesh, and a Prometheus port-forward
(`kubectl -n monitoring port-forward svc/prometheus 9090:9090`). The harness
checks these before starting, records every trial including errors and
inconclusive runs, and restores `ml/defender_actions.jsonl` after remediation
trials. If it is interrupted, run
`python scripts/experimental_validation.py restore-frozen` before retrying.

The current harness also records per-poll anomaly observations, the selected
stress pod and its before/after UID. Those fields are absent from the published
20-trial run and only apply to new runs; `make experimental-summary` reports
their availability.

## Media capture (optional)

```powershell
.\.venv\Scripts\python.exe -m pip install playwright Pillow imageio-ffmpeg
.\.venv\Scripts\python.exe -m playwright install ffmpeg
make demo-media          # live battle + Grafana; needs the Kind lab and port-forward
make demo-media-offline  # committed-evidence dashboard walkthrough; no lab needed
make demo-media-v12      # earlier v1.2 AI Reasoning assets; never overwrites v1.1 media
make demo-media-ai-battle # latest checkbox/fresh-notes assets; mocked API, no keys
```

`make demo-media` regenerates all four original assets with the already-running
local services and Microsoft Edge. It runs a real battle and captures live
Grafana, so check cleanup with `attacker.cli status` afterwards.
`make demo-media-offline` refreshes `dashboard.png`, `demo.gif` and `demo.mp4`
from the evidence already in the running UI; it never runs a battle and leaves
`grafana.png` untouched. `make demo-media-v12` writes only `v12_dashboard.png`,
`v12_ai_reasoning.png`, `v12_demo.gif` and `v12_demo.mp4`, so the four v1.1
assets stay byte-identical. `make demo-media-ai-battle` writes only the six
`v12_ai_battle_*` files (`checkbox.png`, `form.png`, `reasoning.png`,
`dashboard.png`, `demo.gif`, `demo.mp4`) and mocks the gate API in the browser, so it needs the
dashboard but no live API, lab, battle or keys. All four targets need Microsoft
Edge, and none is part of `make verify`.

## Common failures

| Message | Fix |
| --- | --- |
| `fatal: not a git repository` | Run commands from `D:\Projects\1\chaosarena`. |
| `kubectl: command not found` | Put `tools/bin` and Docker resources on `PATH` (see above). |
| `Cannot reach the gate API` | Start `make gate-api` in another terminal. |
| `Access to fetch blocked by CORS` | Use `127.0.0.1:5173` or `4173`; both are allowlisted. |
| `npm ci` fails | Commit `dashboard/package-lock.json`; do not delete it. |
| `Q table not found` | Run `make rl-train`. |
| Battle score below threshold | Check deductions in `ml/last_battle.json`; rerun with a longer settle window. |

## What is never tested in CI

Real attacks, real Kubernetes mutations and the optional Groq call. This keeps
the free workflow deterministic, fast and safe while preserving full local
verification.
