# Technical demonstration audit — 2026-11-20

This pass audited the **real** release-gating workflow in the project's isolated
local environment. No mocked gate response, synthetic API fixture or fabricated
result was used for any cluster-facing check. The committed headline evidence in
`ml/` was preserved; new live-run artifacts are kept separately under
[`docs/audit/`](audit/).

## Environment

| Component | Version / state observed |
| --- | --- |
| Host | Windows 11, Python 3.11 virtualenv at `D:\Projects\1\chaosarena\.venv` |
| Docker Desktop | engine 29.9.3; daemon started for this audit |
| Kind | v0.23.0 at `tools\bin\kind.exe` |
| Cluster | `chaosarena`, one `kindest/node:v1.30.0` control-plane node |
| kubectl / helm | v1.30.0 / v3.15.4 at `tools\bin\` |
| Chaos Mesh | 2.8.8, CRDs installed, controller and daemon healthy |
| Observability | Prometheus and Grafana in `monitoring`; Prometheus reached through `kubectl -n monitoring port-forward svc/prometheus 9090:9090` |
| Test namespaces | `shop-test`, `shop-prod`, `monitoring` |

Before any attack: all pods in the four namespaces were `Running`, readiness
gates passed, `attacker.cli status` reported `chaos_objects: []`, and the
`attacker`, `defender`, `controller`, `rl` and `ci` guards all succeeded.

## What was verified

### 1. Real Kind + Chaos Mesh execution

Two live battles were run with the documented headline command:

```powershell
.\.venv\Scripts\python.exe -m controller.cli evaluate --attack network-latency --target payment-service --duration 30 --threshold 70 --settle 45 --version release-candidate
```

The first attempt before starting the Prometheus port-forward failed in
`defender.cli detect`; after starting the documented port-forward the command
completed and generated real Chaos Mesh objects, Defender detection/remediation
attempts, a score and a gate decision.

| Run | Detection | Recovery | Score | Verdict | Artifact |
| --- | --- | --- | --- | --- | --- |
| Initial calibrated run | 0.0 s | no | 65/D | BLOCK | [`live_battle_2026-11-20.json`](audit/live_battle_2026-11-20.json) |
| After documented baseline retraining | not detected | 37.2 s | 70/C | PROMOTE | [`live_battle_recalibrated_2026-11-20.json`](audit/live_battle_recalibrated_2026-11-20.json) |

Both outcomes are real measurements from this environment. Neither replaces the
committed 13.3 s / 76.2 s / 100/A headline evidence, which came from an earlier
live run on the same project.

### 2. Evidence generation

Each run wrote the full `last_battle.json` bundle (`battle`, `score`, `decision`),
a `last_attack.json` attacker result, an append-only `gate_decisions.jsonl` row
and, when remediation was attempted, a `defender_actions.jsonl` row. Copies of
the live files are in [`docs/audit/`](audit/).

The initial run recorded `action_taken = restart · product-service · requested`
at `2026-11-20T14:41:13+00:00`; the recalibrated run recorded no diagnosis and no
action because the detector never fired.

### 3. Scoring recomputation

`ci.gate check` re-scored both artifacts from battle facts only and ignored the
stored verdicts:

```text
live_battle_2026-11-20.json              -> BLOCK, 65, D  (passed --expect BLOCK)
live_battle_recalibrated_2026-11-20.json -> PROMOTE, 70, C (passed --expect PROMOTE)
```

The deductions were exactly the ones implied by the evidence:
`service did not return to a normal score (-25)` and
`final anomaly score is still above threshold (-10)` for the BLOCK run, and
`fault was never detected (-30)` for the PROMOTE run. This confirms the gate does
not trust a saved decision.

### 4. Decision history

`ml/gate_decisions.jsonl` grew from 19 to 21 lines during the two live runs. The
newest rows were:

```text
2026-11-20T14:42:17+00:00 BLOCK   65 D release-candidate network-latency payment-service
2026-11-20T14:47:24+00:00 PROMOTE 70 C release-candidate network-latency payment-service
```

`GET /gate/history?limit=4` returned those rows newest-first and matched the tail
of the JSONL file exactly. After the audit, the file was restored to its committed
19-line state so the dashboard and docs continue to show the curated demo state.

### 5. Incident report consistency

The offline template reporter was run against each live artifact with the global
`--evidence` option:

```powershell
.\.venv\Scripts\python.exe -m reporter.cli --evidence <artifact> report --backend template --out <output>
```

Both generated reports contain the required six sections and match the artifact
facts exactly. They are preserved as
[`live_report_block_2026-11-20.md`](audit/live_report_block_2026-11-20.md) and
[`live_report_recalibrated_2026-11-20.md`](audit/live_report_recalibrated_2026-11-20.md).

### 6. Cleanup verification

After each battle, `attacker.cli status` reported `chaos_objects: []` and every
pod in `shop-test` was `Running`. The `finally`/`atexit` cleanup path therefore
worked under real Chaos Mesh conditions. No chaos object was left behind.

## Findings

1. **Prometheus port-forward is a required live-battle prerequisite.** Without
   `kubectl -n monitoring port-forward svc/prometheus 9090:9090`, the defender
   cannot query metrics and `controller.cli evaluate` fails before generating
   evidence. This was a documentation gap, not a product defect; the runbook now
   lists it explicitly.

2. **The detector baseline is sensitive to the load profile.** After the host
   restart, live synthetic load was about 2 req/s per service while the committed
   40-sample baseline was collected at roughly 10–26 req/s. Before any attack,
   `defender.cli detect` reported `1.1184` (threshold `0.7397`) and the diagnoser
   blamed `product-service` with `p95_latency z=+1435.6`. Running the documented
   recalibration

   ```powershell
   .\.venv\Scripts\python.exe -m defender.cli baseline --samples 40 --interval 3 --window 30s
   .\.venv\Scripts\python.exe -m defender.cli train
   ```

   produced threshold `0.7539` and a normal pre-attack score of `0.546`. This is
   consistent with the documented limitation that a 40-sample baseline suits
   steady synthetic load only.

3. **Live reproductions are not bit-for-bit deterministic.** With the recalibrated
   baseline, the same 30-second `network-latency` command recovered in 37.2 s but
   never crossed the detector threshold, yielding `-30` and 70/C/PROMOTE. This is
   the same honest failure mode already documented for short faults that disappear
   inside Prometheus's 30-second window, now observed in a different environment.
   It also shows why the score is not a speed claim and why the committed evidence
   should not be overwritten by an arbitrary rerun.

4. **The audit paths themselves were healthy.** Gate recomputation, history append
   and ordering, template reporting and Chaos Mesh cleanup all behaved as
   designed on both live runs.

## Restored state

After capturing the artifacts, these tracked files were restored byte-for-byte
from a pre-audit backup so the committed demo state, tests and docs remain
consistent:

- `ml/last_battle.json`
- `ml/last_attack.json`
- `ml/gate_decisions.jsonl`
- `ml/defender_actions.jsonl`
- `ml/baseline.csv`
- `ml/defender_model.joblib`

The live artifacts under `docs/audit/` are additive evidence and do not change
the dashboard or the published results.

## Untested in this pass

- Bad-release, no-Defender and Defender-value experiments were **not rerun**.
  Their committed evidence comes from earlier real local runs and remains
  described in [RESULTS.md](RESULTS.md).
- The optional Groq reporter backend was not called; no API key was used. Only the
  offline template backend was exercised.
- No multi-node Kind cluster, cloud runner, production workload or external
  traffic generator was used.
- No browser, mobile-device or cross-browser UI retest was performed in this pass;
  the visual QA pass was completed separately.
- No live battle was run on GitHub Actions. The workflow continues to re-score
  saved fixtures only, as documented.

## Limitations

- A single-node Kind cluster on WSL2 does not reproduce production networking or
  scheduler behaviour.
- Loadgen output and Prometheus scrape alignment vary after host/cluster
  restarts, so exact detection times, grades and verdicts are not guaranteed on a
  rerun. Recalibrate the detector only when deliberately establishing a new
  baseline, and restore committed evidence when demonstrating the published
  results.
- The detector diagnoser identifies the strongest symptomatic service, not proof
  of fault origin; the initial audit run blamed `product-service` while the fault
  targeted `payment-service`.
- `controller.cli evaluate` exits non-zero on a BLOCK decision. A scripted demo
  must treat that as the expected bad-release path, not a crash.
