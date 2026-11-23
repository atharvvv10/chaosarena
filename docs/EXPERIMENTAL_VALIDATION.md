# ChaosArena v1.1 Experimental Validation

This report documents a focused research and validation milestone. It does not
redesign the dashboard, change the scoring policy, retrain the detector, or
overwrite the v1.0 demo evidence. All measurements in this report come from real
runs against the isolated `kind-chaosarena` lab or from held-out samples scored
with the frozen v1.0 model. Offline seeded benchmarks remain clearly separate.

Machine-readable records are committed under `ml/experimental_validation/`:

- `trials.jsonl` — every live trial, including errors and inconclusive runs.
- `holdout_normal.jsonl` — independent normal-operation samples.
- `summary.json` — recomputable statistics, both sign tests, holdout caveats and
  frozen-evidence hashes.

## 1. Experimental questions and hypotheses

### Q1 — Can the Defender's remediation genuinely address a controlled fault?

The Defender can only restart or scale allowlisted `shop-test` deployments. It
cannot delete Chaos Mesh objects, repair network rules, or change configuration.
We therefore selected a pod-scoped fault whose stressed pod can plausibly be
removed by the existing `rollout restart` action.

- **Fault:** `cpu-stress` on `order-service`, 120 s.
- **Why this fault:** `StressChaos` with `mode: one` loads one selected pod. A
  restart can replace that pod. This is a *plausible mechanism*, not a proven
  result. Network latency/loss/partition were not used for an effectiveness
  claim because restart/scale cannot remove Chaos Mesh network rules.
- **Hypothesis H1:** Defender-enabled trials show a higher recovery success
  rate or shorter recovery time than observe-only trials under the same fault.
- **Null hypothesis H0:** Recovery is explained by fault-duration expiry,
  Chaos Mesh cleanup and Kubernetes self-healing; the Defender action adds no
  measurable benefit.

### Q2 — Does the detector generalise to normal traffic it never saw?

- The shipped model is trained and thresholded on all 40 rows of
  `ml/baseline.csv`; the published "0 false positives" number is an in-sample
  resubstitution result.
- **Hypothesis H2:** The frozen detector keeps a low false-positive rate on new
  normal-operation windows collected after the v1.0 calibration.
- **Evaluation:** new samples are scored with `ml/defender_model.joblib` only.
  No row is used for training, threshold selection, or retuning.

### Q3 — What does the release gate do under these conditions?

The existing `score_battle()` and `evaluate_gate()` functions are reused without
modification. Each trial is scored from its recorded facts and receives a
score/grade/verdict. This tests gate behaviour on new evidence; it does not
change the policy to obtain better verdicts.

## 2. Environment and methodology

### 2.1 Environment

- Isolated Kind cluster: `kind-chaosarena`, namespace `shop-test` only.
- Chaos Mesh faults are applied through `attacker.cli`, which enforces the
  existing hard allowlist and always cleans labelled objects.
- Prometheus is reached through
  `kubectl -n monitoring port-forward svc/prometheus 9090:9090`.
- Detector input remains the same 18 Prometheus-derived features (request rate,
  error rate and p95 latency for six services).
- Gate threshold: `70` (unchanged default).
- Model and baseline: frozen v1.0 artifacts. Their SHA-256 hashes are recorded
  in `summary.json`.

### 2.2 Paired trial design

- Configurations:
  - **defender-enabled:** detect → diagnose → `defender.cli run --act` → verify.
  - **observe-only:** polls `defender.cli detect` at the same cadence; never
    diagnoses, acts or verifies.
- 10 trials per configuration, 20 total.
- Order alternates by pair (`A/B`, then `B/A`) to reduce order effects.
- Parameters: attack duration `120 s`, poll interval `3 s`, post-attack settle
  `180 s`, calm-start settle `180 s`, Defender verification wait `10 s`, CLI
  timeout `240 s`.
- Before every trial the harness calls `attacker.cli cleanup` if needed and
  waits for a below-threshold detector sample. The existing `BattleRunner`
  implements this; v1.1 added a `remediate=False` path, defaulting to the
  original behaviour.
- Every trial is appended as soon as it terminates. Failures, timeouts and
  `inconclusive_no_detection` results are retained, not discarded.
- The 20 recorded trials used the first harness version. After review, the
  harness now also continues read-only polling after detection, records the
  anomaly span and first normal sample during the attack, and snapshots the
  selected stress pod and its UID. Those fields are therefore `null`/absent for
  the recorded trials below and are available only for future runs; they have
  **not** been back-filled.

### 2.3 Measurement definitions

| Measure | Definition |
| --- | --- |
| Detection | First anomaly observation after attacker launch, on the shared 3 s poll clock. |
| Recovery | Final post-cleanup Prometheus sample has a finite score, valid boolean anomaly, `score <= threshold` and `anomaly == false`. |
| Recovery time | Elapsed time from attacker launch to that authoritative final sample, taken **after the attacker process ends**. Includes up to one 30 s Prometheus window of observation lag. This is a lower bound on true healing time and cannot see recovery earlier than attack duration. |
| Anomaly span (future runs) | Elapsed time from first to last anomalous poll during the attack. A lower bound from the 3 s poll grid; not captured in the 20 recorded trials. |
| First normal after detection (future runs) | First sub-threshold, non-anomalous poll after the first detection. For enabled trials this is after the restart; not captured in the 20 recorded trials. |
| Automatic recovery | Recovery in observe-only trials, where no Defender action occurred. |
| Defender-attributable recovery | Only supportable if enabled trials differ materially from observe-only trials *and* the mechanism is consistent with the action taken. Recovery after Chaos Mesh expiry alone is not attributable to the Defender. |
| Gate outcome | Existing `score_battle()` + `evaluate_gate()` applied to the trial facts. |

Summary statistics are computed over terminal trials only: count, mean, median,
minimum, maximum, range, sample standard deviation, quartiles and IQR. Rates use
the number of terminal trials as the denominator unless stated otherwise.

### 2.4 Held-out normal data

- 30 samples, each from a separate 30 s Prometheus window.
- Sampling interval: 35 s, so windows do not overlap.
- Each sample requires zero active labelled chaos objects and non-zero loadgen
  request rate.
- The sample vector, score, threshold, anomaly decision, timestamp, model hash
  and baseline hash are recorded.
- False-positive rate is `FP / valid samples`. With zero false positives, the
  report also gives the exact one-sided 95% Clopper-Pearson upper bound
  `1 - 0.05^(1/n)`, which is intentionally wide for a small holdout.

### 2.5 Preservation of v1.0 evidence

The harness writes only under `ml/experimental_validation/`. The Defender CLI
appends to `ml/defender_actions.jsonl` when it acts, so the harness snapshots
that file before the run and restores it in a `finally` block. It hashes the
full published evidence set before and after the run and records both hashes in
`summary.json`. It never calls `record_battle`, `record_decision` or
`write_report`, and uses a trial-specific attacker log instead of
`ml/last_attack.json`.

## 3. Trial-level results and summary statistics

All 20 trials terminated; none timed out. One Defender-enabled trial is recorded
as `inconclusive_no_detection` and is retained. All trials cleaned up with zero
labelled chaos objects remaining. The full record is
`ml/experimental_validation/trials.jsonl`.

| Trial | Configuration | Detected | Detection (s) | Recovered | Recovery (s) | Score/grade | Gate | Defender action |
| ---: | --- | --- | ---: | --- | ---: | --- | --- | --- |
| 01 | defender-enabled | yes | 29.0 | yes | 124.3 | 85/B | PROMOTE | restart@order-service |
| 01 | observe-only | yes | 62.4 | yes | 144.2 | 85/B | PROMOTE | none |
| 02 | observe-only | yes | 101.6 | yes | 144.5 | 85/B | PROMOTE | none |
| 02 | defender-enabled | yes | 27.8 | yes | 124.0 | 85/B | PROMOTE | restart@order-service |
| 03 | defender-enabled | yes | 31.4 | yes | 124.2 | 85/B | PROMOTE | restart@order-service |
| 03 | observe-only | yes | 56.6 | yes | 149.3 | 85/B | PROMOTE | none |
| 04 | observe-only | yes | 54.5 | yes | 142.7 | 85/B | PROMOTE | none |
| 04 | defender-enabled | yes | 46.5 | yes | 124.0 | 85/B | PROMOTE | restart@order-service |
| 05 | defender-enabled | yes | 9.2 | yes | 124.1 | 100/A | PROMOTE | restart@order-service |
| 05 | observe-only | yes | 9.1 | yes | 147.1 | 100/A | PROMOTE | none |
| 06 | observe-only | yes | 36.0 | yes | 123.9 | 85/B | PROMOTE | none |
| 06 | defender-enabled | yes | 13.5 | yes | 124.2 | 100/A | PROMOTE | restart@order-service |
| 07 | defender-enabled | **no** | — | yes | 153.0 | 70/C | PROMOTE | none |
| 07 | observe-only | yes | 14.0 | yes | 142.9 | 100/A | PROMOTE | none |
| 08 | observe-only | yes | 14.1 | yes | 128.8 | 100/A | PROMOTE | none |
| 08 | defender-enabled | yes | 18.8 | yes | 124.2 | 100/A | PROMOTE | restart@order-service |
| 09 | defender-enabled | yes | 9.3 | yes | 124.2 | 100/A | PROMOTE | restart@order-service |
| 09 | observe-only | yes | 9.5 | yes | 142.7 | 100/A | PROMOTE | none |
| 10 | observe-only | yes | 108.6 | yes | 143.9 | 85/B | PROMOTE | none |
| 10 | defender-enabled | yes | 9.4 | yes | 124.3 | 100/A | PROMOTE | restart@order-service |

### Summary statistics

| Metric | Defender-enabled | Observe-only |
| --- | --- | --- |
| Terminal trials | 10 | 10 |
| Status counts | 9 completed, 1 inconclusive | 10 completed |
| Detected | 9/10 (90%) | 10/10 (100%) |
| Detection mean / median | 21.66 / 18.80 s | 46.64 / 45.25 s |
| Detection min–max (range) | 9.2–46.5 s (37.3) | 9.1–108.6 s (99.5) |
| Detection stdev / IQR | 12.93 / 20.85 s | 36.96 / 48.40 s |
| Recovered | 10/10 (100%) | 10/10 (100%) |
| Recovery mean / median | 127.05 / 124.20 s | 141.00 / 143.40 s |
| Recovery min–max (range) | 124.0–153.0 s (29.0) | 123.9–149.3 s (25.4) |
| Recovery stdev / IQR | 9.12 / 0.20 s | 8.08 / 1.80 s |
| Defender actions | 9 restarts | 0 |
| Gate verdicts | 10 PROMOTE | 10 PROMOTE |
| Score distribution | 5×100/A, 4×85/B, 1×70/C | 4×100/A, 6×85/B |

The recovery distribution for Defender-enabled trials is extremely tight apart
from trial 07, where the detector never crossed threshold and no action was
taken. The observe-only distribution is also tight but sits about 19 s higher
in the median.

## 4. Defender-enabled versus observe-only comparison

### Detection

- Defender-enabled: 9/10 detected; the miss is trial 07.
- Observe-only: 10/10 detected.
- Detection times vary widely and the observe-only mean is more than twice the
  Defender-enabled mean, but **detection happens before remediation**, so this
  difference cannot be caused by the restart. It is most plausibly explained by
  where `mode: one` placed the stressor and by load/metric variability. The
  experiment does not support a claim that remediation improved detection.

### Recovery

- Automatic recovery occurred in **all 10 observe-only trials** with no Defender
  action. Chaos Mesh duration expiry, cleanup and Kubernetes self-healing are
  sufficient for this fault.
- The paired recovery difference (observe-only minus Defender-enabled) was
  positive in **8 of 10 pairs**, negative in 2:
  - median **+19.15 s**, mean **+13.95 s**, range **−10.1 to +25.1 s**,
    stdev **11.68 s**, IQR **15.9 s**.
  - The two negative pairs are trial 06 (−0.3 s) and trial 07 (−10.1 s, the
    no-detection trial with no Defender action).
- **Measurement floor:** the primary `recovery_seconds` value is taken only
  after the 120 s attacker process ends. Enabled trials cluster at 124.0–124.3 s
  (IQR 0.2 s), essentially attack end plus the final sample; observe-only trials
  wait for the 30 s metric window to clear and sit near 143 s. The 19 s median
  gap therefore mixes a possible real effect with this measurement asymmetry.
  The updated harness now records the anomaly span and the first normal sample
  during the attack, but those fields are absent from the 20 recorded trials, so
  the earlier healing time cannot be quantified retroactively.
- **Primary exact sign test (all 10 pairs):** 8 positive, 2 negative, 0 ties;
  two-sided **p = 0.109375**. This is not conclusive at the 0.05 level.
- **Exploratory post-hoc subgroup (9 pairs where the Defender acted):** 8
  positive, 1 negative, 0 ties; two-sided **p = 0.039062**. This conditions on
  an outcome that occurs after randomisation and is reported only beside the
  primary test, never as the headline result.
- When the Defender acted, it always diagnosed `latency_spike` and issued
  `restart@order-service`. Recovery then clustered near 124 s, consistent with
  replacing the stressed pod. This is **mechanistically compatible** with a
  Defender-attributable timing benefit for this specific fault, but the
  measurement floor above prevents a clean timing claim.

### Verdict

This experiment provides **suggestive but not conclusive** evidence that the
Defender reduced recovery time for `cpu-stress@order-service` when it detected
and restarted the affected deployment. The primary sign test is p = 0.109375;
the smaller post-hoc acted subgroup reaches p = 0.039062 but is exploratory. It
does **not** show that the Defender was necessary for recovery: observe-only
recovered in every trial. It does not show improved detection (one enabled trial
missed the fault), and it does not generalise to network faults, bad releases,
multi-node clusters or production traffic. The causal mechanism was not directly
verified because the recorded trials did not capture which pod received the
stressor or whether the restart replaced that exact pod; the harness now does
so for future runs.

## 5. Detector evaluation results

### Dataset separation

| Role | Data | Use |
| --- | --- | --- |
| Training | all 40 rows of `ml/baseline.csv` | fitted the Isolation Forest, mean/std and deviation term in v1.0 |
| Calibration | the same 40 training rows | set threshold `0.7397` as the 99th percentile plus margin |
| Evaluation | 30 new samples in `ml/experimental_validation/holdout_normal.jsonl` | scored only with the frozen model; never used for fitting or threshold changes |

Model SHA-256: `12e92c681ab34658ce4420cd1f0bd62fc6b0b630ac00839667abd10c3e31033e`.
Baseline SHA-256: `8efa128c543e6bb9d6005e4124e7c5295417c390f76851cbba5c15c5cfb6226c`.
Both are unchanged from the v1.0 evidence set.

### Held-out false-positive behaviour

| Metric | Result |
| --- | --- |
| Collected samples | 30 |
| Valid samples | 30 (zero active chaos, non-zero loadgen request rate) |
| Sampling interval | 35 s, greater than the 30 s Prometheus window |
| False positives | **0 / 30** |
| Observed FPR | **0.0%** |
| Exact one-sided 95% upper bound | **9.5034%** |
| Score mean / median | 0.61 / 0.61 |
| Score min–max (range) | 0.55–0.67 (0.12) |
| Score stdev / IQR | 0.03 / 0.04 |
| Threshold | 0.7397 |

Interpreting this honestly: the frozen detector produced **no false alarms** on
30 held-out normal-operation windows. That is a real check on data unused for
training or thresholding, unlike the v1.0 offline benchmark's in-sample "0 false
positives". It is still a small sample: the exact one-sided 95% upper bound is
about **9.5%**, so these data do not support a production-grade claim such as
"FPR below 1%".

**Correlation caveat:** all 30 windows came from one steady load session, 35 s
apart. Neighbouring windows share traffic conditions and the detector's Markov
smoothing, so they are not 30 fully independent draws. The binomial bound above
assumes independence and is therefore optimistic; the true uncertainty is wider
than 9.5%. A stronger holdout would use multiple sessions and load levels.

### Detection sensitivity

No independent, labelled per-sample fault dataset was collected. The real
Chaos Mesh trials provide trial-level labels (fault injected or not), so the
sensitivity evidence available here is the detection rate reported in section 4:
9/10 for Defender-enabled and 10/10 for observe-only. This should not be read as
sample-level sensitivity or as validation of the seeded 160-row synthetic fault
benchmark.

## 6. Unexpected findings and limitations

### Unexpected findings

1. **A non-detected trial still received `PROMOTE`.** Trial 07 defender-enabled
   never crossed the anomaly threshold, so no diagnosis or action occurred. The
   unchanged policy deducts 30 points for non-detection, leaving exactly 70/C,
   which meets the unchanged gate threshold of 70. Cleanup and final anomaly
   checks still passed. This shows that, as currently defined, the gate is not a
   hard "must detect" gate. The policy was **not** changed to alter this outcome.
2. **Observe-only detection was more variable and later.** Its detection range
   was 9.1–108.6 s versus 9.2–46.5 s in the enabled group. Because remediation
   happens only after detection, this difference cannot be credited to the
   restart. It most likely reflects random stressor placement and metric
   variability.
3. **One observe-only trial recovered as fast as the enabled cluster.** Trial 06
   recovered in 123.9 s with no action, so a Defender timing benefit is not
   universal across fault placement.

### Limitations

- `cpu-stress` uses `mode: one`. The recorded trials did not capture which pod
  received the stressor or whether the restart replaced that exact pod, so the
  proposed mechanism remains plausible rather than directly verified. The
  harness now records the selected pod, its UID and the before/after UID change
  for future runs.
- **The primary recovery metric has a floor.** It is read after the 120 s
  attacker process ends, so the tight 124 s enabled cluster cannot show earlier
  healing. The new during-attack anomaly-span metrics are not available for the
  recorded trials.
- All observe-only trials recovered automatically. Defender value here is at
  most a timing difference, not necessity.
- Recovery time includes the 30 s Prometheus observation window and is not the
  physical time to heal.
- The sample is 10 trials per configuration on one single-node Kind cluster,
  one workload, one fault and one detector version. It is not a production or
  multi-node result. The primary sign test (8/10, p = 0.109375) is consistent
  with "not conclusive"; the acted-subgroup p = 0.039062 is post-hoc and should
  not be used as the headline.
- The holdout tests false positives only. Real labelled per-sample fault vectors
  were not collected, so detector sensitivity is reported only as trial-level
  detection under a known injected fault.
- The 30 holdout windows are correlated samples from one load session. Even zero
  false positives yields an optimistic one-sided 95% upper bound of 9.5%; this
  is a small-sample sanity check, not a production FPR guarantee. Collecting
  across sessions/load levels is future work.
- No lab reconfiguration was performed after measurement began, and no v1.0
  evidence file was changed.

## 7. Reproduction instructions

### 7.1 Prerequisites

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
docker info --format '{{.ServerVersion}}'
kubectl -n monitoring port-forward svc/prometheus 9090:9090
.\.venv\Scripts\python.exe -m attacker.cli ready
.\.venv\Scripts\python.exe -m defender.cli ready
.\.venv\Scripts\python.exe -m attacker.cli status
```

The last command must report `chaos_objects: []`. Do not run these experiments
unless the lab context is `kind-chaosarena`.

### 7.2 Commands

```powershell
make experimental-validation  # or: python scripts/experimental_validation.py run --trials 10
make experimental-holdout     # or: python scripts/experimental_validation.py holdout --samples 30
make experimental-summary     # recompute statistics without touching the lab
```

If a run is interrupted, restore the frozen evidence before retrying:

```powershell
.\.venv\Scripts\python.exe scripts/experimental_validation.py restore-frozen
```

### 7.3 Cluster-free verification

```powershell
.\.venv\Scripts\python.exe scripts/verify_all.py
.\.venv\Scripts\python.exe scripts/technical_demo.py
```
