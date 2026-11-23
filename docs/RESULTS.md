# ChaosArena — Final Results

This is the single place to see what was built and what was actually measured.
Every number below came from a local run on one laptop, not from a slide deck.
Anything labelled **offline** is a seeded, reproducible benchmark, not a live
cluster battle.

## Phase summary

| Phase | Deliverable | Measured result |
| --- | --- | --- |
| 1 | 5 FastAPI services + loadgen, shared observability, Kustomize, Prometheus/Grafana/Loki | Local Python run + Docker Compose + Kind deploy verified; 9 tests |
| 2 | Chaos Mesh 2.8.8, 7 attacks, hard `shop-test` allowlist, guaranteed cleanup | `clusterScoped=true`; 18 tests; cleanup always runs; 0 leftover objects |
| 3 | Defender detect → diagnose → request repair → verify | Isolation Forest + capped deviation; real latency attack diagnosed `latency_spike` on `order-service`, requested a restart, recovered; offline detector comparison added; 16 tests |
| 4 | Arena Controller, Resilience Score, gate, API | Early **Phase 4 score 65 / BLOCK** was a settle-timing artefact; the headline battle now waits for a normal baseline, scores 100/A, detects in 13.3 s and recovers in 76.2 s; 12 tests |
| 5 | Incident reporter, offline + free Groq opt-in | `ml/incident_report.md` and `ml/incident_report_groq.md` with all six sections; 16 tests |
| 6 | Free GitHub Actions resilience gate | Recomputes score from facts; bad fixture BLOCK, good fixture PROMOTE; 9 tests; latest push green |
| 7 | Local React dashboard | 7 tests; `npm run build` clean; browser battle detected and scored 100 PROMOTE, cleanup ok, 0 objects |
| 8 | Free tabular RL attacker | 18 tests; 200 sim episodes; offline learned-vs-random benchmark shows 1.77× more damage than chance |
| 9 | Final docs, results, tests and UI polish | 17 tests; one `make verify`, real screenshots/GIF/video, evidence/baseline/experiment checks, recruiter README and claim/benchmark guards |

**Total: 130 automated tests pass.** Phase 9 contributes 17 tests: 12 phase polish checks plus 5 evidence/experiment checks (evidence API, observe-only baseline, live bad-release gate, timing docs and media). Eight later regression tests cover report refresh in both the API and CLI, abnormal final recovery, missing or invalid final measurements, readiness separation, shared report-path behaviour and the matching frontend assertions.

## Headline gated battle

The committed battle used by CI is `ml/last_battle.json`. It is a real, locally
recorded `network-latency` attack on `payment-service` (`release-candidate`):

| Fact | Measured value |
| --- | --- |
| Detected | yes, in **13.3 s** from attacker launch |
| Diagnosed | `latency_spike` on `order-service` (confidence 0.99, z=+403.7; symptomatic service, not necessarily the attack origin) |
| Action | `restart` requested for `order-service` in `shop-test` |
| Recovered | yes, anomaly score back below threshold in **76.2 s** |
| Cleanup | `cleanup_ok: true`, `chaos_objects_remaining: 0` |
| Score / grade / verdict | **100 / A / PROMOTE** at threshold 70 |
| Deductions | none |

`detection_seconds` is measured from attacker launch to the first anomaly
observation. The controller now waits for a normal baseline before launching, so
the headline's **13.3 s** is on the same clock as the no-Defender control. The
previous `0.0 s` was a measurement artefact: the battle started while the prior
run was still inside Prometheus's 30-second window. `ml/last_battle.json` carries
the basis explicitly in `detection_basis`. A `0.0 s` value is used only in the
bad-release run, where the release was already failing before the battle began.

**Why 100/A despite a 76.2 s recovery.** The score is intentionally simple:
it checks whether the fault was detected, whether it recovered at all, whether
cleanup succeeded, whether the final anomaly score is below threshold, and
whether the attacker reported an error. It does **not** reward faster recovery.
`recovery_seconds` is reported separately and is measured by polling
`defender.cli detect`, so it includes up to one 30-second Prometheus
scrape/window of observation lag. The 100/A therefore means "detected,
recovered and cleaned up", not "recovered quickly". The no-Defender control
recovered sooner on the same clock, so the slow time is not evidence that the
Defender helped.

CI independently recomputes the score from these facts; it never trusts the
stored decision. The earlier 10-second `network-partition` demo scored
**70 / C / PROMOTE** with `detected: false` because the fault healed inside the
30-second Prometheus window. The unfinished-looking result is explained in
`README.md` and preserved in `PORTFOLIO_POLISH.md`; the headline above uses a
sustained fault the Defender can clearly see.

The deliberately bad fixture `ci/fixtures/failing_battle.json` is score 0, grade F,
**BLOCK**, with six deductions. Both directions are tested.

## No-Defender control run

To check whether the Defender's restart was what fixed the fault, the same
`network-latency` fault was run once with **no remediation at all**
(`scripts/no_defender_baseline.py`). The script only polls `defender.cli detect`;
it never calls `diagnose`, `act`, `run` or `verify`, and the controller is not
involved. Evidence: `ml/no_defender_baseline.json`.

| Fact | With Defender (gated battle) | No Defender remediation |
| --- | --- | --- |
| Fault | `network-latency` → `payment-service`, 30 s | same |
| Detected | yes, at 13.3 s | yes, at 10.3 s |
| Repair | `restart` requested on `order-service` | none (observe-only) |
| Recovered | 76.2 s | 50.8 s |
| Final anomaly score | 0.5548 | 0.6576 (threshold 0.7397) |
| Cleanup | ok, 0 objects | ok, 0 objects |

The no-remediation run recovered **without any repair action**, and sooner than
the gated run. These are two single local runs, not a statistical study, but
**for this fault, recovery was not attributable to the Defender**. This does not
prove the Defender is useless: detection and diagnosis still ran, and production
incidents may not self-heal. A restart also may not fix Chaos Mesh latency,
because the chaos can reattach to the new pod. The question "did the restart fix
it?" gets **no supporting evidence** here.

## Bad release vs rollback

To test a release that a rollback can actually fix, `scripts/bad_release_experiment.py`
sets `PAYMENT_FAILURE_RATE=1.0` on the live payment deployment (every payment
fails), runs the same `network-latency` battle through the real controller and
gate, then rolls the env var back to `0.01` and reruns it. Evidence:
`ml/bad_release_experiment.json`.

| Release | Detection | Recovery | Final score | Verdict |
| --- | --- | --- | --- | --- |
| `bad-payment-v2` (`PAYMENT_FAILURE_RATE=1.0`) | 0.0 s (already failing) | never | 65 / D | **BLOCK** |
| `payment-v1-rollback` (`PAYMENT_FAILURE_RATE=0.01`) | 13.2 s | 77.3 s | 100 / A | **PROMOTE** |

The gate **BLOCKed** the bad release and **PROMOTEd** the rollback on the same
battle. The bad-release battle records `detection_seconds: 0.0` because the
release was already failing before the attack started; it is not a clean-start
measurement. This is one pair of local runs, not a statistical guarantee, but it
is a direct live-gate demonstration rather than a saved-fixture self-test.

This **65/D/BLOCK** is a different result from the old **Phase 4 65/BLOCK**
timing artefact. The bad-release BLOCK came from a real release that failed to
recover; the Phase 4 BLOCK came from measuring before the Prometheus window
cleared.

The rollback was performed by the experiment script with `kubectl set env`, not
by the Defender. In the bad-release run the Defender requested a restart of
`order-service` and labelled the fault `latency_spike` (confidence 0.99) even
though the evidence included `order-service_error_rate z=+99.2` and
`payment-service_error_rate z=+93.6`. The Defender did **not** identify the bad
config. The **gate** caught the bad release; do not credit the Defender with that
result.

## Inconclusive CPU-stress control

A `cpu-stress` pair on `order-service` was also attempted with
`scripts/defender_value_experiment.py` (`ml/defender_value_experiment.json`).
The with-Defender run detected at 11.2 s and recovered at 62.8 s. The
no-Defender run **never crossed the anomaly threshold**, so there is no valid
timing comparison. This pair is recorded but **not used as evidence of Defender
value**: a single-pod CPU stressor can land on a pod that is not carrying enough
traffic to move the service-level metrics. The bad-release experiment above is
the stronger, reproducible demonstration.

## Learned vs random attacker

The Q-table is useful only if it finds worse attacks than chance. Seeded offline
simulator, 200 episodes, seed 7; per-fault effectiveness comes from recorded
Phase 3/4 battles. Evidence: `ml/rl_benchmark.json`, regenerate with
`python -m rl.cli benchmark`.

| Policy | Avg damage (0–100) | Avg resilience score |
| --- | --- | --- |
| Uniform random | 16.9 | 83.1 |
| **Learned Q-learning** | **30.0** | **70.0** |

The learned attacker converges on `network-partition@payment-service` and does
**1.77× more damage than random** (13.1 more resilience points lost on average).
This is a reproducible offline benchmark, not a live cluster battle.

## Detector comparison

Same labelled data for all three detectors: the committed 40-sample normal
baseline plus 160 seeded fault signatures (latency spike, error spike, traffic
drop, subtle multi-service latency). Evidence: `ml/defender_benchmark.json`,
regenerate with `python -m defender.cli benchmark`.

| Detector | Precision | Recall | F1 | False positives |
| --- | --- | --- | --- | --- |
| Rule-based (3-sigma) | 99.4% | **100%** | 0.997 | 1 / 40 normal |
| Isolation Forest only | n/a | 0% | 0.000 | 0 / 40 normal |
| **Defender (forest + capped deviation)** | **100%** | 76.2% | 0.865 | **0 / 40 normal** |

Honest reading:

- A simple 3-sigma rule catches every seeded spike, but false-alarms on normal
  traffic and needs hand-set per-feature limits.
- A plain Isolation Forest catches **none**: with 18 features it dilutes a
  single-service spike until it looks normal. This is why the Defender adds a
  bounded standardized-deviation term — it lifts recall from 0% to 76%.
- The shipped Defender keeps **zero false positives**. The remaining misses are
  small error-rate spikes. Precision over recall is the right trade for a
  release gate, where a false alarm blocks a good build.

All three use statistics learned from the same normal baseline, so the
comparison is like-for-like. These are offline benchmarks, not live battles.

## Honest scope

- The early score 65 / BLOCK was caused by measuring before the 30-second
  Prometheus window cleared. It was a settle-timing fix, **not** a bad release
  being caught.
- GitHub Actions re-scores **saved JSON fixtures**; it never runs a live cluster
  battle.
- The RL attacker is **tabular Q-learning**, not PPO or deep RL.
- The 40-sample baseline fits a steady synthetic demo, not production traffic.
- A bad release **was** measured: the live gate BLOCKed `PAYMENT_FAILURE_RATE=1.0`
  at **65/D** and PROMOTEd the `0.01` rollback at **100/A**. That verdict came
  from the gate, not the Defender: the script performed the rollback and the
  Defender mislabelled the failure as `latency_spike` on `order-service` despite
  error-rate z-scores of **+99.2** and **+93.6**.
- Recovery speed was **not** improved by the Defender in the network-latency
  control: **76.2 s** with a requested restart versus **50.8 s** without one.
  Do not claim improved recovery times.
- The **100/A** is not a fast-recovery score. The gate checks detection,
  recovery yes/no, cleanup, final anomaly score and attacker errors; it does not
  reward speed. `recovery_seconds` includes up to one 30-second Prometheus
  observation window.

## GitHub Actions

Workflow: `.github/workflows/ci.yml`
Badge: see the top of `README.md`.

- Free `ubuntu-latest` runner, public repo, no secrets, no cluster.
- Actions used: `checkout@v7.0.1`, `setup-python@v7.1.0`, `setup-node@v7.1.0`.
- Steps: safety guard → pytest → React build → bad-battle BLOCK → good-battle PROMOTE → audit trail.
- Latest push green. The latest run is checked after push.

## Cost statement

No paid accounts, no paid CI minutes (public repo), no hosted database, no paid
UI kit, no marketplace action, no paid LLM API. Groq is strictly optional and
free-tier only; the default reporter is fully offline.

## Links

- [Build notes](BUILD_NOTES.md)
- [Portfolio polish](PORTFOLIO_POLISH.md)
- [Phase 1 ShopApp](phase1.md)
- [Phase 2 attacks](phase2.md)
- [Phase 3 Defender](phase3.md)
- [Phase 4 controller](phase4.md)
- [Phase 5 reporter](phase5.md)
- [Phase 6 CI](phase6.md)
- [Phase 7 dashboard](phase7.md)
- [Phase 8 RL attacker](phase8.md)
- [Phase 9 polish](phase9.md)
- [Testing guide](TESTING.md)
