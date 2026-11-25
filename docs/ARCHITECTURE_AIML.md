# ChaosArena v1.2 — Deep AIML architecture

> Released under tag `v1.2`. The tagged `v1.1` release and its evidence are unchanged.

## The three AI layers

| Layer | Model | Code | Checkpoint |
|---|---|---|---|
| Attacker | **DQN** — MLP 10→64→64→7, replay buffer, target network | `rl/dqn_agent.py`, `rl/deep_arena.py`, `rl/features.py` | `ml/deep/dqn.pt` |
| Defender | **LSTM autoencoder** over 18-feature windows, reconstruction error | `defender/neural.py`, `defender/neural_cli.py` | `ml/deep/defender_lstm.pt` |
| Reasoning | Mixed free-tier LLMs: attacker Groq, defender Gemini, report Groq; offline template fallback | `reporter/role_clients.py`, `attacker/strategist.py`, `defender/analyst.py`, `reporter/cli.py` | none |

## Why three keys across two providers

Each reasoning role owns its own key so one role's traffic cannot exhaust
another's quota. The live map is:

| Role | Provider | Key variable | Default model |
|---|---|---|---|
| Attacker strategist | Groq | `GROQ_ATTACKER_KEY` | `openai/gpt-oss-20b` |
| Defender analyst | Gemini | `GEMINI_DEFENDER_KEY` | `gemini-3.5-flash-lite` |
| Report writer | Groq | `GROQ_REPORT_KEY` | `openai/gpt-oss-20b` |

Copy `.env.example` to a gitignored `.env` and replace the placeholders with
**freshly rotated** keys. Never paste real keys in chat or commit them. Real
shell variables take precedence over `.env`.

`GROQ_API_KEY` and `GEMINI_API_KEY` remain shared per-provider fallbacks.
Backends default to the offline `template` client, so CI and tests never need a
key. The live check uses each role's preferred backend automatically. Inspect
the config without revealing values:

```bash
python -m scripts.llm_guard
python -m scripts.llm_live_check
```

`llm_live_check` calls all three roles, records latencies/cache hits to
`ml/deep/llm_live_check.json`, and **never writes key values**.

## Commands

```bash
# Train offline (no cluster, no key)
python -m rl.train_dqn --episodes 200 --steps 12
python -m defender.neural_cli train --epochs 250

# Compare deep vs classical and write ml/deep/validation.json
python -m scripts.deep_validation --episodes 30 --samples 30

# LLM-assisted reasoning (set the matching key first)
python -m attacker.strategist --backend groq --observation '{"score":65}'
python -m defender.analyst --backend gemini --facts '{"top_features":["payment-service_p95_latency"]}'
python -m reporter.cli --evidence ml/last_battle.json report --backend groq --out ml/deep/incident_report_groq.md

# Real Kind/Chaos Mesh battle with advisory roles (requires the lab + keys)
python -m scripts.live_deep_battle --attack pod-kill --target order-service --duration 30 --settle 60

# Dashboard equivalent: tick "AI battle" before clicking "Run battle". The gate
# API runs the same role-scoped advisory step after the real battle and writes
# fresh notes to ml/deep/live/runtime/ for GET /ai/reasoning.
```

## Safety

- The attacker still has **one hard allowlist** of seven attack/target pairs
  (`rl/arena.py`). LLM output is validated against it before use.
- The LLM never calls Kubernetes, Prometheus or the gate. It only proposes text.
- Every proposal is cached, retried twice, and falls back to a deterministic
  strategy on any error or rate limit.
- The DQN and neural defender are CPU-only and seeded; checkpoints are committed
  so CI only needs inference, not long training runs.

## Validation result (committed at `ml/deep/validation.json`)

- DQN attacker: `30/30` seeded simulator episodes better than tabular
  Q-learning. This is a simulator outcome, not an independent statistical trial:
  the simulator reward makes repeated attacks easier to detect, which the
  vector-state DQN can exploit while the tabular state cannot. No p-value is
  claimed.
- Detector comparison on the same seeded holdout (30 normal and 30 anomalous
  windows built from the committed baseline):

  | Detector | Detections / 30 | False alarms / 30 |
  | --- | ---: | ---: |
  | LSTM autoencoder | **30** | **3** |
  | Shipped Defender (forest + capped deviation) | 0 | **0** |
  | Rule-based (3-sigma) | **30** | 7 |
  | Isolation Forest only | 0 | **0** |

  The LSTM is exploratory and is **not** in the live control loop. It detects
  every seeded spike but raises three false alarms; the shipped Defender keeps
  zero false alarms, which matters more for a release gate. This holdout is
  different from the 40-sample + 160-injection benchmark in
  [RESULTS.md](RESULTS.md), where the shipped Defender reaches 76.2% recall at
  zero false positives.

## Live LLM check (committed at `ml/deep/llm_live_check.json`)

Single real run with three fresh role keys:

- Attacker Groq: `675.6 ms`, allowlisted `pod-kill@order-service`, `60s`; cached replay `0.0 ms`.
- Defender Gemini: `7,471.4 ms`, category `Performance / Availability Degradation`, confidence `0.72`.
- Report Groq: `1,406.1 ms`, `1,305` chars.

Latencies are one observation each, not a benchmark. The JSON records only
`key_set` flags, latencies, cache hits and results — never key values.

## Live lab battle (committed at `ml/deep/live/`)

A real Kind/Chaos Mesh battle was rerun for v1.2 on a fresh baseline isolated
under `ml/deep/live/`:

- Fault: `pod-kill@order-service` for 30 s.
- Detected in `15.8 s`, recovered in `53.1 s`, score `100/A/PROMOTE`.
- Cleanup ok, 0 chaos objects remaining.
- Groq proposed the attack idea, Gemini made separate pre-battle and post-battle
  calls, and Groq wrote the report from the recorded facts.
- The dashboard exposes these through `GET /ai/reasoning` in an **AI Reasoning**
  panel. Only role names, latencies, rationales and results are returned. A
  dashboard battle with **AI battle** enabled writes fresh advisory notes to
  `ml/deep/live/runtime/`, including the same two distinct Gemini roles, and
  that endpoint prefers the complete fresh set over the committed run.
- Latest `v12_ai_battle_*` screenshots/GIF/MP4 show that panel and the checkbox;
  the v1.1 media files are
  preserved byte-identical.

Full record, including the first `network-latency` false negative and why the
baseline was isolated: [V12_LIVE_VALIDATION.md](V12_LIVE_VALIDATION.md).

**Caveats:** the simulator profiles are teaching priors from earlier real runs;
the holdout windows are seeded perturbations, not live traffic. The live lab
result is one battle, not a statistical study. No v1.1 evidence, scoring, raw
trial data, UI capture or media was modified; new `v12_*` media was added beside
the frozen originals.
