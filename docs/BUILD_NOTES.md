# Build Notes

These are the original build/verification notes moved out of the README so the
project pitch stays readable. They record what was actually run on one laptop.

## Local setup on this machine

See [local-setup.md](local-setup.md) — installed tool versions and WSL2 setup.
See [phase2.md](phase2.md) — the 7 attacks, hard allowlist, cleanup design and
measured results. Chaos Mesh is installed in the `chaos-mesh` namespace.
See [phase3.md](phase3.md) — the Defender's model, bounded actions and the full
detect → diagnose → request repair → verify result.
See [phase4.md](phase4.md) — the battle, score rules, gate decision and API.
See [phase5.md](phase5.md) — the incident report, offline backend and free Groq setup.
See [phase6.md](phase6.md) — the free GitHub Actions workflow and CI gate.
See [phase7.md](phase7.md) — the React dashboard, API additions and browser verification.
See [phase8.md](phase8.md) — the free tabular Q-learning attacker, simulator and real battle.
See [phase9.md](phase9.md) — final docs, one-command verification and UI polish.
See [dashboard/README.md](../dashboard/README.md) — how to run the UI next to the gate API.

## Verify Phase 1

```bash
make smoke
kubectl -n shop-test get pods
kubectl -n monitoring logs deploy/promtail --tail=20
```

In Grafana, open **Dashboards → ShopApp → ChaosArena - ShopApp Live**. You should see
non-zero lines for all five services in the request-rate, error-rate and latency panels.

## Build verification actually performed

- `pytest` → **77 passed** at the end of Phase 6 (services and metrics; allowlist,
  all 7 manifests, cleanup; model, diagnosis, bounded actions; score, gate, audit
  log, API; facts, prompt, report, offline + free Groq; workflow, gate self-test,
  recomputed verdict). The suite grew to **122 passed** after the final evidence, baseline and bad-release checks.
- All five services + loadgen launched via `scripts/run_local.py` on a machine with
  **no Docker, no WSL2, no kubectl and no make**.
- Live end-to-end flow succeeded: register → JWT login → catalogue → cart add →
  payment → order create → order read. Example order: `total 13.5`, `status paid`,
  `version v1.0.0`.
- Live `/metrics` emitted `http_requests_total` and the latency histogram with
  counts incrementing after real HTTP calls.
- After WSL2 was activated, the full Kubernetes path was executed for real:
  Docker Desktop engine 29.9.3, Kind cluster `chaosarena` (1 control-plane node),
  6 images built and loaded, and all manifests applied to `shop-test`, `shop-prod`
  and `monitoring`.
- Prometheus scrapes **22 healthy pod targets** with non-zero request-rate and
  latency data; Grafana 11.2.0 serves the 6-panel `ChaosArena - ShopApp Live`
  dashboard; Loki receives structured logs via Promtail with `namespace`, `pod`
  and `container` labels.
- In-cluster end-to-end order: `total 13.5`, `status paid`, read back successfully
  through a port-forward to `order-service`.
- Phase 2: Chaos Mesh 2.8.8 installed; all 7 manifests passed server-side dry-run;
  `pod-failure` cleaned up with zero remaining objects; `network-latency` moved
  order-service p95 from **0.24 s → 0.845 s → 0.24 s** (before / during / after).
- Phase 3: 40-sample baseline trained to threshold **0.7397**. During a real
  latency attack the Defender scored **1.123**, diagnosed `latency_spike` on
  `order-service` (`z=+237.6`), requested a restart in `shop-test`, and verification
  returned **0.586** with `recovered: true`. No attacker import in `defender/`.
- Phase 4: the first `network-latency` battle scored **65 / BLOCK** because the
  final Prometheus sample was still inside the attack window — a measurement
  timing issue, not a rejected bad release. This old 65 is distinct from the
  live bad-release **65/D/BLOCK** recorded later. A bounded settle period fixed
  the measurement; the next battle scored **100 / PROMOTE** for `v1.0.1`.
  `/gate/evaluate` also ran a `pod-kill` battle live through uvicorn; decisions
  are in `ml/gate_decisions.jsonl`. No attacker/defender import in `controller/`.
- Phase 5: a fresh 20-second battle produced `ml/last_battle.json`; the offline
  reporter wrote a six-section `ml/incident_report.md` using only recorded facts.
  Groq's **free** tier is wired in (`openai/gpt-oss-20b`) for a real-model report
  with only `GROQ_API_KEY`. A real free-tier Groq call wrote
  `ml/incident_report_groq.md` with all six sections and the correct battle facts.
- Phase 6: `.github/workflows/ci.yml` runs tests and the resilience gate on
  GitHub's free `ubuntu-latest` runner. It re-scores **saved** passing and failing
  fixtures (100/`PROMOTE`, 0/`BLOCK`) and ignores a tampered stored decision.
  No cluster, live attack, secrets, cloud or paid action is required.

> Note: `infra/k8s/observability/promtail.yaml` uses a static `__path__` tail plus
> pipeline stages. This is intentional for the single-node Kind cluster — it avoids
> Kubernetes service-discovery edge cases and was verified with real log entries.

## About the 40-sample baseline

The Defender was trained on 40 normal-traffic samples collected 3 seconds apart
over a 30-second Prometheus window. That is enough for this demo because the
traffic pattern is stationary (loadgen generates the same steady request mix) and
the detector only needs a stable threshold for one reproducible attack scenario.
For production you would collect many days across peak/off-peak cycles, re-fit
periodically, add drift detection and validate against a held-out incident set.
