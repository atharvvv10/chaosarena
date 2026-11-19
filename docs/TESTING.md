# Testing Guide

## One command

```powershell
cd D:\Projects\1\chaosarena
make verify
```

This runs `python scripts/verify_all.py`: every pytest suite, all four safety
guards, the CI gate fixture checks, and the React production build. It needs no
cluster, no internet and no secret.

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
| `pytest -q tests/test_phase6.py` | Free workflow YAML, tamper-proof CI gate |
| `pytest -q tests/test_phase7.py` | Dashboard API, CORS, free packages, panels |
| `pytest -q tests/test_phase8.py` | RL safety, Q-learning, sim/real paths |
| `pytest -q tests/test_phase9.py` | Final docs, RL policy API, polish, no-paid scan |

## Cluster-dependent checks (manual)

These are intentionally not in CI because CI has no cluster:

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
.\.venv\Scripts\python.exe -m attacker.cli status
.\.venv\Scripts\python.exe -m attacker.cli guard
.\.venv\Scripts\python.exe -m defender.cli guard
```

Expected: `chaos_objects: []`, all pods `Running`.

To run one real gated battle:

```powershell
.\.venv\Scripts\python.exe -m controller.cli evaluate --attack network-partition --target payment-service --duration 10 --threshold 70 --settle 20
```

Or let the RL attacker choose:

```powershell
.\.venv\Scripts\python.exe -m rl.cli real --episodes 1 --duration 10 --settle 20 --threshold 0
```

Always confirm cleanup afterwards with `attacker.cli status`.

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
