# Phase 8 — RL Attacker (sim + real)

## What this phase adds

A small **tabular Q-learning attacker** that learns which allowlisted fault is
hardest for the Defender to handle. It has two environments with the same
`step(action)` interface:

- **SimArena** — a deterministic, cluster-free teaching environment seeded from
  the scores measured in Phases 3 and 4. Training takes milliseconds and needs
  no internet, account or paid library.
- **RealArena** — runs one real battle through the public `controller.cli`
  interface, reads its JSON, and updates the Q table from the real reward.

The learner cannot invent an attack, touch `shop-prod`, or call Kubernetes.
Real execution is limited to three attack/target pairs already proven in earlier
phases.

## Plan (executed)

1. Build a fixed action space from the seven Phase 2 attacks and the verified
   targets, with a stricter real-mode allowlist.
2. Implement `QLearningAgent`: epsilon-greedy choice, Q update, epsilon decay,
   JSON save/load — standard library only.
3. Implement `SimArena` and `RealArena`, both returning score, reward, next state
   and facts.
4. Add `python -m rl.cli guard|train|policy|real`, including `--dry-run`.
5. Add 14 acceptance tests covering safety, learning, persistence and the real
   CLI path with mocked subprocesses.
6. Train 200 simulated episodes, run one real battle, verify cleanup, then push.

## Files created / changed

| Path | Purpose |
| --- | --- |
| `rl/__init__.py` | Public exports for the RL package. |
| `rl/arena.py` | `Action`, `ACTION_SPACE`, `REAL_ACTION_ALLOWLIST`, `SimArena`, `RealArena`. |
| `rl/agent.py` | Tabular Q-learning agent with epsilon-greedy policy and JSON persistence. |
| `rl/cli.py` | `guard`, `train`, `policy`, `real` commands. |
| `tests/test_phase8.py` | 14 acceptance tests (no cluster needed). |
| `ml/rl_q_table.json` | Trained Q table, committed as reproducible evidence. |
| `Makefile` | `rl-guard`, `rl-train`, `rl-policy`, `rl-real`, `rl-real-dry`. |
| `README.md` | Status, checklist and docs links updated. |

No dependency changes: `requirements-dev.txt` is unchanged. No `torch`,
`tensorflow`, `gym`, cloud SDK or API key is used.

## Commands used

```powershell
# Safety rules
.\.venv\Scripts\python.exe -m rl.cli guard

# Fast learning, no cluster
.\.venv\Scripts\python.exe -m rl.cli train --episodes 200 --seed 7
.\.venv\Scripts\python.exe -m rl.cli policy

# See exactly what real mode would run (safe, no cluster)
.\.venv\Scripts\python.exe -m rl.cli real --dry-run

# One real battle (needs the local Kind cluster)
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
.\.venv\Scripts\python.exe -m rl.cli real --episodes 1 --duration 10 --settle 20 --threshold 0

# Offline learned-vs-random benchmark (no cluster; writes ml/rl_benchmark.json)
.\.venv\Scripts\python.exe -m rl.cli benchmark
```

## Verified results

- **130 tests passed at the Phase 8 snapshot**; this phase contributed 18 tests, and v1.2 raised the suite to the current total in [RESULTS.md](RESULTS.md).
- Simulator trained for 200 episodes; epsilon decayed `1.0 → 0.05`.
- Learned calm-state ranking:
  1. `network-partition@payment-service` — Q = 1.4999
  2. `pod-kill@order-service` — Q = 1.1138
  3. `network-loss@order-service` — Q = 0.9744
- `real --dry-run` produced only:
  `python -m controller.cli evaluate --attack network-partition --target payment-service ...`
- Real RL battle: **score 70, grade C, PROMOTE**, `detected=false`,
  reward `0.3`, next state `alert`. Q for the chosen action rose `1.4999 → 1.5`.
- Cluster after the battle: `chaos_objects: []`, all listed pods `Running`.
- `ci.gate check --evidence ml/last_battle.json --threshold 70 --expect PROMOTE`
  still passes with the RL battle as evidence.
- Offline learned-vs-random benchmark (`ml/rl_benchmark.json`): learned damage
  **30.0** vs random **16.9** (resilience **70.0** vs **83.1**), i.e. **1.77×**
  more damage. This is a seeded simulator result, not a live battle; see
  [RESULTS.md](RESULTS.md#learned-vs-random-attacker).

## How the reward works

```
reward = (100 - resilience_score) / 100
```

The Defender's score already penalises missed detection, no recovery, failed
cleanup, leftover chaos objects and attacker errors. Reusing it means the agent
is optimising the **same objective the release gate measures**, without a
second, hidden scoring system.

State is deliberately tiny:

- `calm` — last observation was detected and handled.
- `alert` — last observation slipped past the Defender.

Q-learning update: `Q(s,a) += 0.3 * [r + 0.8 * max Q(s',a') - Q(s,a)]`.

## Common errors and fixes

| Problem | Cause | Fix |
| --- | --- | --- |
| `refuses unproven action` | Real mode picked an attack/target pair not yet verified | Use only keys in `REAL_ACTION_ALLOWLIST`, or verify a new pair first. |
| `controller.cli produced no JSON` | Cluster tools missing or controller crashed | Add `tools/bin` and Docker to `PATH`, then rerun `attacker.cli status`. |
| `Q table ... not found` | `policy`/`real` ran before training | Run `python -m rl.cli train`. |
| Real battle left the gate evidence as `BLOCK` | Threshold too low/high relative to score | Use `--threshold 0` for a safe demo, or restore a known `PROMOTE` battle. |
| Learning looks random | Epsilon still high early on | Train more episodes; epsilon decays to `0.05`. |
| Worried this needs a GPU or paid RL service | It is a plain Python dictionary of numbers | No ML framework, no network call, no account. |

## Why these choices

- Tabular Q-learning is honest and inspectable: every learned value is one JSON
  number, so there is no opaque model or expensive training job.
- The simulator is a **teaching prior**, not a physics model. Real adaptation
  happens only in `RealArena`, through the same public CLI the controller uses.
- Restricting real mode to proven pairs keeps Phase 2's safety guarantee intact
  while still allowing full exploration in simulation.
- The RL package never imports `defender/`, preserving Phase 3's isolation rule.

## Cost check

Standard Python only. Sim training needs no cluster and no internet. Real mode
uses the same free local Kind cluster as earlier phases. Nothing is billed.

## Phase 8 status

Complete locally, including one real learned battle and a clean cluster. GitHub
Actions is checked after push.
