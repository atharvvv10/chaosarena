# ChaosArena v1.2 — Deep AIML architecture

> Work in progress on branch `v1.2-deep-aiml`. The tagged `v1.1` release and its
> evidence are unchanged.

## The three AI layers

| Layer | Model | Code | Checkpoint |
|---|---|---|---|
| Attacker | **DQN** — MLP 10→64→64→7, replay buffer, target network | `rl/dqn_agent.py`, `rl/deep_arena.py`, `rl/features.py` | `ml/deep/dqn.pt` |
| Defender | **LSTM autoencoder** over 18-feature windows, reconstruction error | `defender/neural.py`, `defender/neural_cli.py` | `ml/deep/defender_lstm.pt` |
| Reasoning | Three role-scoped LLM clients (Groq by default, offline template fallback) | `reporter/role_clients.py`, `attacker/strategist.py`, `defender/analyst.py`, `reporter/cli.py` | none |

## Why three keys

Each reasoning role owns its own Groq key so one role's traffic cannot exhaust
another's quota:

```powershell
$env:GROQ_ATTACKER_KEY = 'gsk_attacker'
$env:GROQ_DEFENDER_KEY = 'gsk_defender'
$env:GROQ_REPORT_KEY   = 'gsk_report'
```

`GROQ_API_KEY` remains a shared fallback. Backends default to the offline
`template` client, so CI and tests never need a key. Inspect the config without
revealing values:

```bash
python -m scripts.llm_guard
```

## Commands

```bash
# Train offline (no cluster, no key)
python -m rl.train_dqn --episodes 200 --steps 12
python -m defender.neural_cli train --epochs 250

# Compare deep vs classical and write ml/deep/validation.json
python -m scripts.deep_validation --episodes 30 --samples 30

# LLM-assisted reasoning (set the matching key first)
python -m attacker.strategist --backend groq --observation '{"score":65}'
python -m defender.analyst --backend groq --facts '{"top_features":["payment-service_p95_latency"]}'
python -m reporter.cli --evidence ml/last_battle.json report --backend groq --out ml/deep/incident_report_groq.md
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

- DQN attacker: `30/30` seeded episodes better than tabular Q-learning,
  exact sign test `p ≈ 2e-09`. The noisy simulator makes repeated attacks easier
  to detect, which the vector-state DQN learns to avoid.
- LSTM defender: `30/30` seeded spike detections with `3/30` false alarms;
  the Isolation Forest detected `0/30` with `0/30` false alarms on the same
  synthetic holdout.

**Caveats:** the simulator profiles are teaching priors from earlier real runs;
the holdout windows are seeded perturbations, not live traffic. No Kubernetes
experiment was rerun and no v1.1 data was modified.
