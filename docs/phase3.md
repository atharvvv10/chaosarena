# Phase 3 — Defender (Isolation Forest detect → diagnose → act → verify)

## What this phase adds

A `defender/` module that watches the same Prometheus metrics a human operator
sees, learns what "normal" looks like, and reacts when something breaks. It has
**no dependency on the attacker package** — it does not know which attack is
running, only that the numbers are wrong.

Safety is the same idea as Phase 2: the defender may only touch `shop-test`,
only six named deployments, and only `restart` or `scale` between 1 and 4
replicas. It cannot delete anything and cannot reach `shop-prod`.

## Files

| Path | Purpose |
|---|---|
| `defender/features.py` | Fixed 18-feature layout (6 services × 3 metrics) |
| `defender/collect.py` | Reads Prometheus; collects/writes the baseline CSV |
| `defender/model.py` | Isolation Forest + deviation term, save/load bundle |
| `defender/diagnose.py` | Ranks deviating features into a category + service |
| `defender/policy.py` | Maps a diagnosis to one bounded action |
| `defender/actions.py` | Allowlisted `restart` / `scale`, writes an audit log |
| `defender/verify.py` | Re-scores after the action to confirm recovery |
| `defender/kubectl.py` | Defender-owned kubectl wrapper |
| `defender/cli.py` | `python -m defender.cli` commands |
| `defender/benchmark.py` | Offline rule-based vs Isolation Forest vs Defender comparison |
| `tests/test_phase3.py` | 16 tests |
| `docs/phase3.md` | This file |
| `Makefile` | `baseline`, `train`, `detect`, `defend`, `defender-guard` |

## The four stages

1. **Detect** — score the current 18-number vector. Above threshold = anomaly.
2. **Diagnose** — find which service/metric deviated most and name the family
   (`latency_spike`, `error_spike`, `traffic_drop`).
3. **Act** — apply one small, logged repair: restart a deployment, or scale it
   to 3 replicas.
4. **Verify** — sample again and check the score is back below threshold.

## Why the score has two parts

A plain Isolation Forest spreads one bad number across 18 features, so a single
service's latency spike can look ordinary. We add a small, capped deviation
term (`max |z| / 100`, capped at `0.5`). The forest is still the core model; the
extra term just makes a big single-service spike visible.

The threshold is the 99th percentile of training scores plus a `0.12` margin.
Normal loadgen traffic moves a few percent between samples, and that margin
stops those normal changes from being called attacks.

## Exact commands

```powershell
cd D:\Projects\1\chaosarena

# 1. Learn normal traffic (40 samples, 3 s apart, 30 s Prometheus window)
.\.venv\Scripts\python.exe -m defender.cli baseline --samples 40 --interval 3 --window 30s
.\.venv\Scripts\python.exe -m defender.cli train

# 2. Check the defender's own boundaries
.\.venv\Scripts\python.exe -m defender.cli guard

# 3. Normal traffic should be clean
.\.venv\Scripts\python.exe -m defender.cli detect

# 4. Attack in one terminal, defend in another
.\.venv\Scripts\python.exe -m attacker.cli attack network-latency --target payment-service --duration 30 --hold 30
.\.venv\Scripts\python.exe -m defender.cli run --act --wait 25

# 5. After the attack is cleaned up
.\.venv\Scripts\python.exe -m defender.cli detect
.\.venv\Scripts\python.exe -m attacker.cli status

# 6. Offline detector comparison (no cluster needed; writes ml/defender_benchmark.json)
.\.venv\Scripts\python.exe -m defender.cli benchmark
```

## Results actually measured on this laptop

Baseline: 40 samples → threshold **0.7397**. Forty samples are enough here because
loadgen produces a steady, repeatable traffic pattern and the detector only needs
one stable threshold for this demo. Production would need days of traffic across
peak/off-peak cycles, drift detection and held-out incidents.

| Moment | Score | Result |
|---|---|---|
| Normal traffic | 0.567 | `anomaly: false` |
| During latency attack | 1.123 | `anomaly: true` |
| After restart + cleanup | 0.586 | `anomaly: false`, `recovered: true` |

The full loop diagnosed **`latency_spike` on `order-service`** (evidence:
`order-service_p95_latency z=+237.6`), chose `restart`, applied it to
`shop-test`, and verification reported `recovered: true`. Chaos cleanup left
zero objects and `attacker.cli status` showed no active experiments.

### Offline detector comparison

`python -m defender.cli benchmark` scores three detectors on the same labelled
data: the 40 recorded normal samples plus 160 seeded fault signatures. The
result is committed at `ml/defender_benchmark.json`.

| Detector | Precision | Recall | False positives |
| --- | --- | --- | --- |
| Rule-based (3-sigma) | 99.4% | 100% | 1 / 40 normal |
| Isolation Forest only | n/a | 0% | 0 / 40 normal |
| Defender (forest + capped deviation) | 100% | 76.2% | 0 / 40 normal |

A plain forest dilutes a single-service spike across 18 features, so the capped
deviation term is what makes detection work; it lifts recall from 0% to 76% with
zero false positives. A 3-sigma rule catches every seeded spike but false-alarms
on normal traffic. These are offline benchmarks, not live battles. Full reading:
[RESULTS.md](RESULTS.md#detector-comparison).

## Common errors and fixes

| Error / surprise | Cause | Fix |
|---|---|---|
| `model not found at ml/defender_model.joblib` | No model trained yet | Run `baseline` then `train` |
| Normal traffic flagged as an anomaly | Baseline collected in a different load phase, threshold too tight | Re-collect baseline with `--window 30s` and retrain |
| Attack not detected in the first 10 seconds | Prometheus `[30s]` rate window needs time to fill | Wait ~10–15 s, or use `run` which samples again |
| `AttackRejected` / `ActionRejected` | Production or unknown service requested | This is the guard working; do not remove it |
| Score stays high after cleanup | `[1m]` window still contains attack data | Use the default `[30s]` window |

## Why the defender cannot cheat

`tests/test_phase3.py` includes `test_defender_does_not_import_attacker`, which
scans every `defender/*.py` file and fails if it mentions the attacker package.
The defender earns its result from observability data only. The action audit
log is `ml/defender_actions.jsonl`, so every repair can be reviewed afterwards.
