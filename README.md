# ChaosArena

[![ChaosArena Resilience Gate](https://github.com/atharvvv10/chaosarena/actions/workflows/ci.yml/badge.svg)](https://github.com/atharvvv10/chaosarena/actions/workflows/ci.yml)

**A resilience-gated CI/CD lab that treats a release like a fight.** A tabular Q-learning attacker injects one of seven allowlisted Chaos Mesh faults into a `shop-test` namespace; an Isolation Forest defender detects, diagnoses and requests a repair; and a controller scores the whole exchange into a `PROMOTE`/`BLOCK` decision. It all runs on one laptop with Kind, Prometheus, Grafana and a React dashboard — no cloud account, paid CI minute, hosted database or API key. The repo ships the tests, saved battle evidence, free GitHub Actions workflow and a recorded demo, so you can see and verify the full loop rather than trust a diagram.

![ChaosArena demo — run a battle, watch the gate and read the learned policy](docs/screenshots/demo.gif)

[Watch the full demo (MP4)](docs/screenshots/demo.mp4) · [Dashboard screenshot](docs/screenshots/dashboard.png) · [Grafana screenshot](docs/screenshots/grafana.png) · [All results](docs/RESULTS.md)

## Evaluate ChaosArena

Choose the level of depth that fits your time.

**Option 1: Quick technical demonstration**

```powershell
.\.venv\Scripts\python.exe scripts/technical_demo.py
```

No running Kubernetes cluster required. The replay reads committed evidence and a real audit artifact, then recomputes the release decision with the project's own gate code. This demonstrates that stored verdicts are not trusted — not that the underlying measurements themselves cannot be altered. [Read the generated transcript](docs/DEMO_TRANSCRIPT.md).

**Option 2: Inspect the dashboard**

Start the existing FastAPI backend and React frontend using the documented setup in [DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md#1-deterministic-demo-from-committed-evidence). No live battle is needed to see the published results.

**Option 3: Reproduce a live experiment**

Follow [DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) to run a controlled battle in the isolated Kind environment. [DEMO_AUDIT.md](docs/DEMO_AUDIT.md) records the last real run and its environmental limitations.

The GIF and MP4 record the detected 100/A battle; the PNG is a full-page capture of the current UI, including the no-Defender recovery-control and bad-release panels.

## Results at a glance

| What | Measured result |
| --- | --- |
| Automated tests | **128 passing**: 9 phase suites plus 6 final regression checks (`make verify`) |
| Chaos attacks | **7** allowlisted faults, `shop-test` only, guaranteed cleanup — **0 objects left** |
| Headline gated battle | **100/100, grade A, PROMOTE** at threshold 70; `network-latency` detected in **13.3 s**, recovered in **76.2 s**, cleanup ok, 0 objects left |
| Defender | Detected in **13.3 s**, recovered in **76.2 s**; diagnosed `latency_spike` on `order-service` (symptomatic, not necessarily the origin); 40-sample baseline (threshold 0.7397) |
| Gate vs bad release | A deliberately bad payment config (`PAYMENT_FAILURE_RATE=1.0`) scored **65/D, BLOCK**; rollback to `0.01` scored **100/A, PROMOTE** on the same battle |
| RL attacker | Learned policy does **more damage than random**: **1.77×** (resilience **70.0** vs **83.1**) in the seeded simulator |
| Detector comparison | Plain Isolation Forest **0% recall**; full Defender **76% recall at 0% false positives** — [details](#detector-comparison) |
| CI | Free `ubuntu-latest` Actions, latest push green, no cluster, no secrets |
| Cost | **$0** — local Kind, free React/Vite, free Actions tier, offline reporter by default |

## Learned vs random attacker

A Q-table is only useful if it finds worse attacks than chance. In the seeded
offline simulator (200 episodes, seed 7, per-fault effectiveness taken from
recorded Phase 3/4 battles):

| Policy | Avg damage (0–100) | Avg resilience score |
| --- | --- | --- |
| Uniform random | 16.9 | 83.1 |
| **Learned Q-learning** | **30.0** | **70.0** |

The learned attacker converges on `network-partition@payment-service` and does
**more damage than random** — 1.77× as much, measured as points taken off the
resilience score. This is a reproducible offline benchmark, **not** a live
cluster battle. Evidence: `ml/rl_benchmark.json`; regenerate with
`python -m rl.cli benchmark`.

## Detector comparison

Same labelled data for all three: the committed 40-sample normal baseline plus
160 seeded fault signatures (latency spike, error spike, traffic drop, and a
subtle multi-service latency rise). Offline and reproducible — evidence in
`ml/defender_benchmark.json`; regenerate with `python -m defender.cli benchmark`.

| Detector | Precision | Recall | False positives |
| --- | --- | --- | --- |
| Rule-based (3-sigma) | 99.4% | **100%** | 1 / 40 normal |
| Isolation Forest only | n/a | 0% | 0 / 40 normal |
| **Defender (forest + capped deviation)** | **100%** | 76.2% | **0 / 40 normal** |

Read this honestly: a simple 3-sigma rule catches every seeded spike but raises
a false alarm on normal traffic. A plain Isolation Forest catches **none** —
across 18 features it dilutes a single-service spike until it looks normal. The
shipped Defender adds a bounded standardized-deviation term that lifts recall
from 0% to 76% while keeping **zero false positives**; the remaining misses are
small error-rate spikes. Zero false positives is the right trade for a release
gate, where a false alarm blocks a good build.

## What is in the loop

1. **Attacker** — seven Chaos Mesh experiments behind a hard `shop-test` allowlist; `finally` cleanup always runs.
2. **Defender** — reads only Prometheus signals, uses Isolation Forest plus a capped deviation term, then detect → diagnose → request a repair → verify. It requests the action; it does not repair by itself. It never imports or reads the attacker.
3. **Controller** — drives both sides through their public CLIs, recomputes the resilience score from observed facts, and records the gate decision and audit trail.
4. **Dashboard + CI** — a local React UI with a section nav, always-visible key results, a real battle timeline, labelled offline benchmark panels, searchable history and report actions, plus a free GitHub workflow that re-scores saved fixtures on every push. See [DASHBOARD.md](docs/DASHBOARD.md).

## Honest scope — read this before an interview

- The early **Phase 4 score 65 / BLOCK** was a *measurement timing* issue: the final Prometheus sample was still inside the attack window. A bounded settle period fixed the measurement; it was **not** a bad release being caught. Do not confuse that old 65 with the live bad-release **65/D/BLOCK** below — they are two different runs.
- GitHub Actions does **not** run a live battle. It re-scores **saved** passing and failing JSON fixtures on a cluster-free runner. The real battles were run locally and their evidence is committed.
- The attacker is **tabular Q-learning** (a JSON Q-table with epsilon-greedy exploration), **not PPO** or a deep RL model.
- The Defender baseline is **40 samples**. That is enough for a deterministic local demo with steady synthetic load; production would need days of traffic across peak/off-peak cycles, drift detection and held-out incidents. See [BUILD_NOTES.md](docs/BUILD_NOTES.md).
- An earlier demo used a **10-second `network-partition`** and scored **70/C/PROMOTE** because the fault healed inside the 30-second Prometheus window and was never flagged. The headline battle instead uses a sustained **30-second `network-latency`** fault that the Defender clearly detects; a repair was requested, but a no-Defender control run recovered without it. Both runs are real; see [PORTFOLIO_POLISH.md](docs/PORTFOLIO_POLISH.md).
- The learned-vs-random and detector-comparison tables are **offline, seeded benchmarks**, not live cluster battles. Their exact commands and data are linked above.
- The diagnoser identifies the symptomatic service, not always the origin. In the headline battle the fault targeted `payment-service`, but `order-service` showed the strongest latency signal and was restarted.
- A no-Defender control run of the same fault recovered in **50.8 s** with no repair action, versus **76.2 s** in the gated run. Two single runs are not a statistical study, but they do not show that the restart caused recovery. See [RESULTS.md](docs/RESULTS.md#no-defender-control-run).
- The headline battle waits for a normal baseline before launching, so its detection time uses the same clock as the control. A `0.0 s` value means the detector was already anomalous at launch, not that detection was instantaneous. Earlier it came from starting a battle while a previous run was still inside Prometheus's 30-second window; in the 2026-11-20 audit it came from a stale baseline after a host restart. That audit artifact is kept separately from the committed headline evidence; see [DEMO_AUDIT.md](docs/DEMO_AUDIT.md).
- The live gate caught a deliberately bad payment release: **65/D/BLOCK** while `PAYMENT_FAILURE_RATE=1.0`, then **100/A/PROMOTE** after rolling back to `0.01`. This is one pair of local runs, not a statistical guarantee; it shows the gate rejected a release that could not pass the resilience check. The rollback was performed by the experiment script, **not** the Defender. In the bad-release run the Defender requested a restart of `order-service` while labelling the failure `latency_spike`, despite `order-service_error_rate z=+99.2` and `payment-service_error_rate z=+93.6`; the gate, not the Defender, identified the release as bad.
- For the network-latency fault, recovery was **not attributable to the Defender**: a no-Defender control recovered on its own. A restart may not fix Chaos Mesh latency because chaos can reattach to the new pod.
- The **100/A** is not a fast-recovery claim. The score checks whether the fault was detected, whether it recovered, cleanup, the final anomaly score and attacker errors; it does not penalise a slow recovery. `recovery_seconds` is reported separately and includes up to one 30-second Prometheus scrape/window of observation lag. The control recovered sooner on the same clock.
- The learned attacker's best action comes from a seeded simulator backed by only a few real battles. Treat it as a demo policy, not a production-trained agent.
- The detector benchmark reuses the same 40 normal samples as the baseline and adds 160 synthetic faults. Treat its F1 numbers as a demo, not production evidence.

## Try it in the dashboard

```text
http://127.0.0.1:5173     dashboard
http://127.0.0.1:8080     gate API
```

1. Click **Refresh** — the header distinguishes `API ONLINE · LAB READY` from `API ONLINE · LAB NOT READY`. The API can be reachable while Kind or Prometheus is unavailable; a live battle needs the lab ready.
2. In **Run a battle**, use: attack `network-latency`, target `payment-service`, duration `30`, settle `45`, threshold `70`, version `release-candidate`.
3. Click **Run battle** and wait about a minute. Do not click twice.
4. Read the **Release gate** card for score/grade/verdict and **Why**. A new row appears in **Decision history**.
5. Check **RL attacker** for the learned policy. In **Incident report**, use **Copy** or **Download**.
6. Use the sticky nav to open **Evidence**: the timeline is the recorded real battle; **Learned vs random** and **Detector comparison** are clearly labelled offline benchmarks. In **History**, search or filter PROMOTE/BLOCK rows.

If the API is offline, start it with `python -m uvicorn controller.api:app --host 127.0.0.1 --port 8080` from the project venv. If the API is online but the lab is not ready, start Kind, deploy the lab and open the Prometheus port-forward described below; the dashboard can still read committed evidence. If the dashboard is closed, run `cd dashboard && npm run dev`.

For a technical evaluator, [DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) gives the exact
committed-state and live-battle commands, and [DEMO_AUDIT.md](docs/DEMO_AUDIT.md)
records what was actually verified in the isolated Kind environment, including
environmental limitations. A live battle requires the Prometheus port-forward
(`kubectl -n monitoring port-forward svc/prometheus 9090:9090`); the dashboard
alone only reads committed evidence unless a live battle is run.

## Fresh clone

```bash
make cluster     # Kind cluster with shop-test, shop-prod, monitoring
make deploy      # build and load 6 images, apply manifests
make metrics     # REQUIRED before a live battle: Prometheus on :9090
make gate-api    # local gate API on :8080
cd dashboard && npm install && npm run dev
make verify      # all cluster-free checks: tests, guards, gate fixtures, UI build
```

`make metrics` blocks, so run it in its own terminal. On Windows, use the
PowerShell equivalents in [local-setup.md](docs/local-setup.md); the `make`
targets call `chmod` and shell scripts. Plain-Python and Docker Compose
alternatives are in [BUILD_NOTES.md](docs/BUILD_NOTES.md).

## Architecture

```mermaid
flowchart LR
    subgraph Laptop["One laptop - Kind cluster"]
        subgraph Test["namespace: shop-test (attacked)"]
            U[user-service] --> P[product-service]
            O[order-service] --> C[cart-service]
            O --> PAY[payment-service]
            C <--> R[(Redis)]
            O --> PG[(PostgreSQL)]
            LG[loadgen] --> U
            LG --> O
        end
        subgraph Prod["namespace: shop-prod"]
            U2[user-service] --> O2[order-service]
        end
        subgraph Mon["namespace: monitoring"]
            PR[Prometheus] --> G[Grafana]
            PT[Promtail] --> L[Loki]
            L --> G
            PR -.scrapes.-> Test
            PT -.tails logs.-> Test
        end
    end
    Attacker[Q-learning attacker] -.Chaos Mesh.-> Test
    Defender[Isolation Forest defender] -.k8s API.-> Test
    Controller[Arena Controller] --> Attacker
    Controller --> Defender
    CI[GitHub Actions / make pipeline] --> Controller
```

## Documentation

- [Final results](docs/RESULTS.md) · [Testing guide](docs/TESTING.md) · [Build notes](docs/BUILD_NOTES.md) · [Portfolio polish](docs/PORTFOLIO_POLISH.md)
- [Phase 1 ShopApp](docs/phase1.md) · [Phase 2 attacks](docs/phase2.md) · [Phase 3 defender](docs/phase3.md) · [Phase 4 controller](docs/phase4.md) · [Phase 5 reporter](docs/phase5.md)
- [Phase 6 CI](docs/phase6.md) · [Phase 7 dashboard](docs/phase7.md) · [Phase 8 RL attacker](docs/phase8.md) · [Phase 9 polish](docs/phase9.md)
- [Dashboard README](dashboard/README.md) · [Dashboard UI and evidence panels](docs/DASHBOARD.md)

Everything here is free and local. No paid service, no cloud account, no secret and no marketplace action is required.
