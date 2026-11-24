# v1.2 live lab validation

This record covers the **v1.2 deep AIML** additive upgrade on the
`v1.2-deep-aiml` branch. It does not replace any v1.1 evidence, score, raw
trial data, UI capture or the `v1.1` tag.

## What was actually run

A real fault was injected into the existing isolated Kind lab:

| Item | Value |
| --- | --- |
| Lab | Docker Desktop + Kind cluster `chaosarena` |
| Namespace | `shop-test` |
| Metrics | Prometheus via `kubectl -n monitoring port-forward svc/prometheus 9090:9090` |
| Fault | `pod-kill` on `order-service` for 30 s |
| Detector | Fresh baseline/model trained only under `ml/deep/live/` |
| Gate threshold | 70 |

Result:

| Measure | Result |
| --- | --- |
| Detected | **yes**, 15.8 s after attacker launch |
| Recovered | **53.1 s** |
| Resilience score | **100 / 100**, grade A |
| Verdict | **PROMOTE** |
| Cleanup | ok, 0 chaos objects left |

Evidence is committed under `ml/deep/live/`:

- `summary.json` — run summary
- `last_battle.json` — full recorded battle
- `last_attack.json` — Chaos Mesh manifest record
- `gate_decisions.jsonl` — gate decision
- `incident_report.md` — Groq-written report from the real facts
- `advisories.json` — Groq attack idea, Gemini preflight note, local DQN ranking
- `defender_analysis.json` — Gemini explanation of the real facts
- `baseline.csv` / `defender_model.joblib` — isolated detector artifacts

## Where the AI APIs were used

| Role | Provider | Latency | What it did |
| --- | --- | ---: | --- |
| Attack idea | Groq | 1,066.1 ms | Proposed `pod-kill@order-service` with a rationale |
| Defender preflight | Gemini | 6,973.2 ms | Explained the planned chaos scenario |
| Local attacker | DQN | 27.4 ms | Ranked `pod-kill@order-service` first (no API) |
| Defender post-battle | Gemini | 1,468.9 ms | Explained the real detection/recovery facts |
| Report | Groq | — | Wrote a validated 1,302-character incident report |

These are **single observed latencies**, not a benchmark.

The earlier three-role check is also committed at
`ml/deep/llm_live_check.json`. It records attacker Groq, defender Gemini and
report Groq with latency, cache-hit and source fields only.

## What the AI does not do

Groq and Gemini never run `kubectl`, create Chaos Mesh objects, change the
release gate or execute remediation. The real fault comes from the fixed
allowlisted CLI:

```text
python -m attacker.cli attack pod-kill --target order-service --duration 30
```

Detection and remediation are owned by `defender.cli` and the classical
Isolation Forest. DQN and the neural detector are local, seeded and CPU-only.

## Why the baseline is separate

After Docker/Kind restarted, the frozen v1.1 detector scored calm traffic as
anomalous (`1.1144 > 0.7397`). Rather than modify v1.1 artifacts, a fresh
baseline and model were collected into `ml/deep/live/`. The first
`network-latency` attempt then produced a real **false negative**; Gemini
flagged it as such. The recorded final battle uses the DQN's top-ranked idea,
`pod-kill@order-service`, and detects it in 15.8 s.

## Where to see it

- Website: **AI Reasoning** section in the dashboard
- API: `GET /ai/reasoning`
- Files: `ml/deep/live/advisories.json`, `defender_analysis.json`, `incident_report.md`
- Docs: [ARCHITECTURE_AIML.md](ARCHITECTURE_AIML.md)

The API returns allowlisted fields only. No API key values are stored in the
repository, evidence files, reports, charts or UI.

## Reproduce

```powershell
python -m scripts.live_deep_battle `
  --attack pod-kill --target order-service `
  --duration 30 --settle 60 --out ml/deep/live
```

This requires the documented Kind lab and Prometheus port-forward. CI runs the
cluster-free tests only and needs no keys.

**Caveat:** this is one live battle, not a statistical study. The GIF/MP4 and
Grafana PNG remain the original v1.1 captures; no media was overwritten.
