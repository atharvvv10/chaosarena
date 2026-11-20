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
| 3 | Defender detect → diagnose → act → verify | Isolation Forest + capped deviation; real latency attack diagnosed `latency_spike` on `order-service`, restarted, recovered; offline detector comparison added; 16 tests |
| 4 | Arena Controller, Resilience Score, gate, API | Early score 65 was a settle-timing artefact; with a settle window the headline battle scores 100/A, detected on the first poll (0.0 s recorded) and recovered in 57.4 s; timing now recorded; 12 tests |
| 5 | Incident reporter, offline + free Groq opt-in | `ml/incident_report.md` and `ml/incident_report_groq.md` with all six sections; 16 tests |
| 6 | Free GitHub Actions resilience gate | Recomputes score from facts; bad fixture BLOCK, good fixture PROMOTE; 9 tests; all runs green |
| 7 | Local React dashboard | 7 tests; `npm run build` clean; browser battle detected and scored 100 PROMOTE, cleanup ok, 0 objects |
| 8 | Free tabular RL attacker | 18 tests; 200 sim episodes; offline learned-vs-random benchmark shows 1.77× more damage than chance |
| 9 | Final docs, results, tests and UI polish | 12 tests; one `make verify`, real screenshots/GIF/video, recruiter README and claim/benchmark guards |

**Total: 121 automated tests pass.**

## Headline gated battle

The committed battle used by CI is `ml/last_battle.json`. It is a real, locally
recorded `network-latency` attack on `payment-service` (`release-candidate`):

| Fact | Measured value |
| --- | --- |
| Detected | yes, on the first poll (**0.0 s** recorded) |
| Diagnosed | `latency_spike` on `order-service` (confidence 0.99, z=+296.5; symptomatic service, not necessarily the attack origin) |
| Action | `restart` requested for `order-service` in `shop-test` |
| Recovered | yes, anomaly score back below threshold in **57.4 s** |
| Cleanup | `cleanup_ok: true`, `chaos_objects_remaining: 0` |
| Score / grade / verdict | **100 / A / PROMOTE** at threshold 70 |
| Deductions | none |

`detection_seconds` is measured from attacker launch to the first anomaly
observation. The recorded `0.0 s` means the anomaly was already present on the
first poll immediately after launch, not that the Defender started observing
before the attack. `ml/last_battle.json` carries this basis explicitly in
`detection_basis`, and the dashboard timeline shows the same clarification.

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
| Detected | yes, first poll (0.0 s recorded) | yes, at 10.3 s |
| Repair | `restart` requested on `order-service` | none (observe-only) |
| Recovered | 57.4 s | 50.8 s |
| Final anomaly score | 0.6320 | 0.6576 (threshold 0.7397) |
| Cleanup | ok, 0 objects | ok, 0 objects |

The no-remediation run recovered **without any repair action**, and slightly
sooner than the gated run. These are two single local runs, not a statistical
study, but they show the restart was **not required for recovery in this
environment**. This does not prove the Defender is useless: detection and
diagnosis still ran, and production incidents may not self-heal. It does answer
the question "did the restart fix it?" with **no evidence that it did** here.

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
- No claim is made about a bad release being blocked or about improved recovery
  times: neither was measured.

## GitHub Actions

Workflow: `.github/workflows/ci.yml`
Badge: see the top of `README.md`.

- Free `ubuntu-latest` runner, public repo, no secrets, no cluster.
- Actions used: `checkout@v7.0.1`, `setup-python@v7.1.0`, `setup-node@v7.1.0`.
- Steps: safety guard → pytest → React build → bad-battle BLOCK → good-battle PROMOTE → audit trail.
- All runs to date are green; the final run is checked after push.

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
