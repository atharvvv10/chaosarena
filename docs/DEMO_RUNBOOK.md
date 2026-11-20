# Technical demonstration runbook

This runbook is for a technical evaluator who wants to understand and reproduce
ChaosArena without changing its architecture. It separates the **deterministic
committed-state demo** from the **optional live Kind battle**. Use the committed
state for the published numbers; use the live path to prove the loop really runs.

For the shortest recruiter-friendly walkthrough, run
`python scripts/technical_demo.py` (or `make technical-demo`). It replays the
architecture, controlled fault, measured evidence, scoring and independent
decision recomputation from recorded facts without touching a cluster. The
generated transcript is
[DEMO_TRANSCRIPT.md](DEMO_TRANSCRIPT.md).

The audit results and the exact live artifacts from the most recent pass are in
[DEMO_AUDIT.md](DEMO_AUDIT.md).

## 0. Prerequisites

From the repository root (`D:\Projects\1\chaosarena` on the documented laptop):

```powershell
$env:PATH = "D:\Projects\1\chaosarena\tools\bin;C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
.\.venv\Scripts\python.exe -m pytest --version
kind version
kubectl version --client --short
helm version --short
docker info --format '{{.ServerVersion}}'
```

`tools/` is gitignored and holds the isolated local toolchain (`kind.exe`,
`kubectl.exe`, `helm.exe`). Docker Desktop must be running so the `chaosarena`
Kind cluster is reachable.

## 1. Deterministic demo from committed evidence

This path needs **no live attack** and reproduces the published dashboard and
results exactly.

```powershell
# 1. Cluster-free verification: 122 tests, six guards, gate fixtures, React build
.\.venv\Scripts\python.exe scripts\verify_all.py

# 2. Start the gate API
.\.venv\Scripts\python.exe -m uvicorn controller.api:app --host 127.0.0.1 --port 8080

# 3. In another terminal, start the dashboard
cd dashboard
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Expected observations:

- **Refresh** → `API online`.
- **Release gate** → `100`, grade `A`, `PROMOTE`, threshold `70`.
- **Battle Timeline** → `network-latency`, detection `13.3 s`, recovery `76.2 s`,
  `restart · order-service · requested`, cleanup OK, 0 objects left.
- **Evidence** → `Resilience comparisons`, `Detector performance`,
  `Attacker learning`; the last two are labelled offline.
- **History** → newest-first rows from `ml/gate_decisions.jsonl`; search and
  PROMOTE/BLOCK filters work.
- **Incident report** → collapsed by default, six numbered sections, Copy and
  Download enabled.

Recheck the committed gate without a cluster at any time:

```powershell
.\.venv\Scripts\python.exe -m ci.gate check --evidence ml/last_battle.json --threshold 70 --expect PROMOTE
.\.venv\Scripts\python.exe -m ci.gate check --evidence ci/fixtures/failing_battle.json --threshold 70 --expect BLOCK
```

Generate the same offline report shown in the dashboard:

```powershell
.\.venv\Scripts\python.exe -m reporter.cli --evidence ml/last_battle.json report --backend template --out ml/incident_report.md
```

> `--evidence` is a global option and must come **before** the `report`
> subcommand.

## 2. Optional live battle on Kind + Chaos Mesh

Use this path to demonstrate real fault injection, detection, scoring, history and
cleanup. Exact numbers will vary with cluster state and scrape timing; do not
overwrite the committed headline evidence unless you intend to publish a new
result set.

### 2.1 Start and verify the isolated environment

```powershell
# Start Docker Desktop if the daemon is not already up.
Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe'

# Confirm or create the documented cluster.
kind get clusters
kubectl cluster-info
kubectl get nodes -o wide

# If the cluster is absent, use the documented setup:
kind create cluster --name chaosarena --config infra/kind-config.yaml
kubectl apply -f infra/k8s/namespaces.yaml
kubectl apply -k infra/k8s/observability
kubectl apply -k infra/k8s/overlays/test
kubectl apply -k infra/k8s/overlays/prod
```

Wait for rollouts and confirm all pods are running:

```powershell
kubectl -n shop-test rollout status deploy/user-service --timeout=240s
kubectl -n shop-test rollout status deploy/order-service --timeout=240s
kubectl -n monitoring rollout status deploy/prometheus --timeout=240s
kubectl get pods -n shop-test -o wide
kubectl get pods -n monitoring -o wide
```

Start the **required** Prometheus port-forward in its own terminal:

```powershell
kubectl -n monitoring port-forward svc/prometheus 9090:9090
```

Without this, `defender.cli detect` cannot query metrics and the battle fails
before any Chaos Mesh object is created.

### 2.2 Preflight guards and clean state

```powershell
.\.venv\Scripts\python.exe -m attacker.cli guard
.\.venv\Scripts\python.exe -m defender.cli guard
.\.venv\Scripts\python.exe -m controller.cli guard
.\.venv\Scripts\python.exe -m ci.gate guard
.\.venv\Scripts\python.exe -m rl.cli guard
.\.venv\Scripts\python.exe -m attacker.cli status
```

Expected: `chaos_objects: []` and all pods `Running`. If chaos objects remain:

```powershell
.\.venv\Scripts\python.exe -m attacker.cli cleanup
```

Confirm the detector is calm **before** launching a fault:

```powershell
.\.venv\Scripts\python.exe -m defender.cli detect
```

The score must be below the printed threshold. If it is already anomalous, the
committed baseline no longer matches current traffic — see §3.

### 2.3 Run the documented headline battle

```powershell
.\.venv\Scripts\python.exe -m controller.cli evaluate --attack network-latency --target payment-service --duration 30 --threshold 70 --settle 45 --version release-candidate
```

This single command performs the whole loop:

1. `attacker.cli status` + cleanup precheck.
2. Baseline `defender.cli detect` and startup settle.
3. Chaos Mesh `NetworkChaos` injection against `payment-service` in `shop-test`.
4. First-anomaly detection, diagnosis and a bounded restart request.
5. Fault cleanup, post-attack settle, score and gate decision.
6. Append to `ml/gate_decisions.jsonl` and overwrite `ml/last_battle.json`.

A `BLOCK` decision makes the CLI exit non-zero; that is expected behaviour, not a
crash. Read the JSON `decision` and `score.deductions`.

### 2.4 Verify the artifacts

```powershell
# Cleanup must be empty.
.\.venv\Scripts\python.exe -m attacker.cli status

# Gate recomputes from facts; choose the expectation matching the decision.
.\.venv\Scripts\python.exe -m ci.gate check --evidence ml/last_battle.json --threshold 70 --expect PROMOTE
# or: ... --expect BLOCK

# Show newest decision and history.
.\.venv\Scripts\python.exe -m controller.cli last
```

If the gate API is running, `http://127.0.0.1:8080/gate/history?limit=10` must
match the tail of `ml/gate_decisions.jsonl` newest-first.

Generate a report from this exact run:

```powershell
.\.venv\Scripts\python.exe -m reporter.cli --evidence ml/last_battle.json report --backend template --out <timestamped-output.md>
```

### 2.5 Preserve or restore state

To keep a live artifact as audit evidence without changing the published demo:

```powershell
New-Item -ItemType Directory -Force docs\audit | Out-Null
Copy-Item ml\last_battle.json docs\audit\live_battle_<timestamp>.json
Copy-Item ml\last_attack.json docs\audit\live_attack_<timestamp>.json
Copy-Item ml\gate_decisions.jsonl docs\audit\gate_decisions_<timestamp>.jsonl
Copy-Item ml\defender_actions.jsonl docs\audit\defender_actions_<timestamp>.jsonl
```

Then restore the committed demo files:

```powershell
git checkout -- ml/last_battle.json ml/last_attack.json ml/gate_decisions.jsonl ml/defender_actions.jsonl
```

Run `.\.venv\Scripts\python.exe scripts\verify_all.py` again after restoring; the
committed 100/A PROMOTE evidence must pass.

## 3. If the detector baseline is stale

A host or cluster restart can change the synthetic load profile. If the
pre-attack `defender.cli detect` already reports `anomaly: true`, the committed
40-sample baseline is not describing current traffic. The documented remedy is:

```powershell
.\.venv\Scripts\python.exe -m defender.cli baseline --samples 40 --interval 3 --window 30s
.\.venv\Scripts\python.exe -m defender.cli train
.\.venv\Scripts\python.exe -m defender.cli detect
```

This writes `ml/baseline.csv` and `ml/defender_model.joblib` and prints a new
threshold. It is valid for a fresh calibration study, but it changes the model
used by the dashboard and docs. Back up both files first and restore them with
`git checkout -- ml/baseline.csv ml/defender_model.joblib` when returning to the
published results.

The recent audit recorded this exact situation: pre-attack score `1.1184`
against `0.7397`, followed by a recalibrated threshold `0.7539` and normal score
`0.546`. See [DEMO_AUDIT.md](DEMO_AUDIT.md#findings).

## 4. Troubleshooting

| Symptom | Cause / action |
| --- | --- |
| `defender.cli detect produced no JSON` | Prometheus port-forward is not running. Start `kubectl -n monitoring port-forward svc/prometheus 9090:9090`. |
| Pre-attack `anomaly: true` | Stale baseline after a restart. Follow §3. |
| `chaos_objects` not empty after a run | Run `attacker.cli cleanup`, then recheck `attacker.cli status`. |
| CLI exits 1 | A BLOCK decision is encoded as exit 1. Read the decision JSON. |
| `Cannot reach the gate API` | Start `python -m uvicorn controller.api:app --host 127.0.0.1 --port 8080`. |
| CORS error in dashboard | Use `127.0.0.1:5173` or `4173`, both allowlisted. |
| History does not match | Check `GET /gate/history`; it reads the newest lines of `ml/gate_decisions.jsonl` and reverses them. |
| Published numbers differ after a live run | Expected. Restore committed evidence with `git checkout --`, or publish a new evidence set with updated docs. |

## 5. Do not do these in a demo

- Do not replace live cluster checks with mocked `/gate/evaluate` responses when
  claiming a live battle. Mocked routes are only acceptable for isolated UI
  interaction tests.
- Do not present `ml/incident_report_groq.md` as the report for the current
  headline battle; it was generated from an earlier v1.0.3 run.
- Do not describe the tabular Q-learning attacker as PPO or deep RL.
- Do not claim the Defender caused recovery. The no-Defender control recovered
  without remediation.
- Do not claim the gate stopped a bad release because of a CI fixture. The
  bad-release 65/D/BLOCK came from a separate real local experiment, and the
  rollback was performed by the experiment script.
