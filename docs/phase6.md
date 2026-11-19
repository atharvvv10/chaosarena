# Phase 6 — GitHub Actions resilience gate

## What this phase adds

A **free** GitHub Actions workflow that runs on every push, pull request and
manual trigger. It does three things:

1. installs the Python dependencies from `requirements-dev.txt`,
2. runs the full test suite,
3. re-scores the recorded battle and **fails the build if the gate says BLOCK**.

It uses only GitHub's free `ubuntu-latest` runner and the official free
`actions/checkout` / `actions/setup-python` actions. It needs **no Kubernetes
cluster, no cloud account, no secrets and no paid marketplace app**. The free
Groq reporter is deliberately not used in CI.

## Files

| Path | Purpose |
|---|---|
| `.github/workflows/ci.yml` | The free workflow (test + gate + audit trail) |
| `ci/gate.py` | Re-scores evidence and enforces `PROMOTE` / `BLOCK` |
| `ci/__init__.py` | Small public API for the checker |
| `ci/fixtures/passing_battle.json` | Known-good battle: score 100, `PROMOTE` |
| `ci/fixtures/failing_battle.json` | Deliberately bad battle: score 0, `BLOCK` |
| `tests/test_phase6.py` | 9 tests for the gate and the workflow |
| `requirements-dev.txt` | Adds `PyYAML==6.0.3` so tests can parse the workflow |
| `Makefile` | `ci-guard`, `ci-selftest`, `ci-check` |
| `docs/phase6.md` | This file |

## How the gate really works

The checker does **not** trust the decision saved in `ml/last_battle.json`.
It reads only the `battle` facts, rebuilds `BattleResult`, calls the Phase 4
`score_battle()` and `evaluate_gate()`, and then compares the fresh verdict with
`--expect`.

- `--expect PROMOTE` → the step passes only if the gate promotes.
- `--expect BLOCK` → the step passes only if the gate blocks.

That second mode is the self-test: it proves the gate logic blocks a deliberately
bad **saved fixture** instead of always saying yes. No live battle runs on the
Actions runner.

## Exact commands (local, same logic as CI)

```powershell
cd D:\Projects\1\chaosarena

# 1. Full suite
.\.venv\Scripts\python.exe -m pytest -q

# 2. See the gate's safety rules
.\.venv\Scripts\python.exe -m ci.gate guard

# 3. Self-test: a deliberately bad battle must BLOCK
.\.venv\Scripts\python.exe -m ci.gate check `
  --evidence ci/fixtures/failing_battle.json --threshold 70 --expect BLOCK

# 4. Enforce the committed battle: must PROMOTE
.\.venv\Scripts\python.exe -m ci.gate check `
  --evidence ml/last_battle.json --threshold 70 --expect PROMOTE
```

On GitHub, push to `main`/`master`, open a pull request, or run the workflow
manually from the **Actions** tab → **ChaosArena Resilience Gate** → **Run
workflow**. No extra setup is needed.

## Results actually measured

- **77 tests pass** (68 earlier + 9 new).
- `ci.gate check` on the passing fixture → `PROMOTE`, score **100**, grade **A**.
- `ci.gate check` on the failing fixture → `BLOCK`, score **0**, grade **F**,
  all six deductions present.
- A tampered fixture with a fake `"verdict": "PROMOTE"` still produced `BLOCK`,
  proving the stored decision is ignored.
- Workflow YAML parsed successfully; it uses `ubuntu-latest`, `contents: read`,
  official free actions, and contains no cloud/self-hosted/paid references.

## Common errors and fixes

| Error / surprise | Cause | Fix |
|---|---|---|
| YAML parser reads `on` as `True` | YAML 1.1 treats bare `on` as a boolean | Workflow uses quoted `'on':`; tests parse it as a string |
| `ModuleNotFoundError: yaml` in CI | PyYAML was only installed locally by chance | Added `PyYAML==6.0.3` to `requirements-dev.txt` |
| Gate step fails with `GATE FAILED: expected PROMOTE, got BLOCK` | The committed battle genuinely failed | Fix the service/defender, run a new `controller.cli evaluate`, commit the new evidence |
| Self-test step fails | Gate is too permissive | Check `controller/score.py` and `controller/gate.py`; failing fixture must score 0 |
| `Node.js 20 is deprecated` warning | Old `checkout@v4` / `setup-python@v5` were forced onto Node 24 | Upgraded to `checkout@v7.0.1` and `setup-python@v7.1.0`; run is clean |
| Worried about billing | GitHub free tier has minute limits for private repos | Public repos are unlimited; this job takes ~1 minute and uses no paid add-ons |

## Why this is safe and free

CI only reads a JSON file and runs Python. It never starts Chaos Mesh, never
touches `shop-prod`, and never sends data to Groq or any cloud. The gate is the
same code Phase 4 used live, so a local `ci-check` and the GitHub step make the
**same decision**. If the demo repo is public, GitHub Actions costs nothing;
if it is private, the free monthly minutes easily cover this short job.
