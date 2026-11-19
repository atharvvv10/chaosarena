# ChaosArena — Final Results

This is the single place to see what was built and what was actually measured.
Every number below came from a local run on one laptop, not from a slide deck.

## Phase summary

| Phase | Deliverable | Measured result |
| --- | --- | --- |
| 1 | 5 FastAPI services + loadgen, shared observability, Kustomize, Prometheus/Grafana/Loki | Local Python run + Docker Compose + Kind deploy verified; 9 tests |
| 2 | Chaos Mesh 2.8.8, 7 attacks, hard `shop-test` allowlist, guaranteed cleanup | `clusterScoped=true`; 18 tests; cleanup always runs; 0 leftover objects |
| 3 | Defender detect → diagnose → act → verify | Isolation Forest + capped deviation; real latency attack diagnosed `latency_spike` on `order-service`, restarted, recovered; 14 tests |
| 4 | Arena Controller, Resilience Score, gate, API | Early score 65 was a settle-timing artefact, not a bad release; with a settle window, PROMOTE 100 and a `pod-kill` API battle 70 PROMOTE; 11 tests |
| 5 | Incident reporter, offline + free Groq opt-in | `ml/incident_report.md` and `ml/incident_report_groq.md` with all six sections; 16 tests |
| 6 | Free GitHub Actions resilience gate | Recomputes score from facts; bad battle BLOCK, good battle PROMOTE; 9 tests; all runs green |
| 7 | Local React dashboard | 7 tests; `npm run build` clean; browser battle score 70 PROMOTE, cleanup ok, 0 objects |
| 8 | Free tabular RL attacker | 14 tests; 200 sim episodes; real battle score 70 PROMOTE, reward 0.3, cluster clean |
| 9 | Final docs, results, tests and UI polish | One `make verify` command; 8 tests; polished dashboard, real screenshots/GIF/video and recruiter-facing README verified |

**Total: 110 automated tests pass.**

## Release gate evidence

The committed battle used by CI is `ml/last_battle.json`. It is the final
dashboard-recorded `network-partition` attack on `payment-service` (`demo-v1`):

- `detected: false` → one documented deduction (-30)
- `recovered: true`, `cleanup_ok: true`, `chaos_objects_remaining: 0`
- score **70**, grade **C**, verdict **PROMOTE** at threshold 70
- CI independently recomputes the score; it never trusts the stored decision.

An earlier dashboard battle in the same recording scored **100 / A / PROMOTE**
with detection at 7.3 s and recovery. The Phase 8 RL-selected battle also scored
**70 / C / PROMOTE**. Both are documented in `PORTFOLIO_POLISH.md` and `phase8.md`.

The deliberately bad fixture `ci/fixtures/failing_battle.json` is score 0, grade F,
**BLOCK**, with six deductions. Both directions are tested.

## Honest scope

- The early score 65 / BLOCK was caused by measuring before the 30-second
  Prometheus window cleared. It was a settle-timing fix, **not** a bad release
  being caught.
- GitHub Actions re-scores **saved JSON fixtures**; it never runs a live cluster
  battle.
- The RL attacker is **tabular Q-learning**, not PPO or deep RL.
- The 40-sample baseline fits a steady synthetic demo, not production traffic.

## GitHub Actions

Workflow: `.github/workflows/ci.yml`
Badge: see the top of `README.md`.

- Free `ubuntu-latest` runner, public repo, no secrets, no cluster.
- Actions used: `checkout@v7.0.1`, `setup-python@v7.1.0`, `setup-node@v7.1.0`.
- Steps: safety guard → pytest → React build → bad-battle BLOCK → good-battle PROMOTE → audit trail.
- All runs to date are green; the Phase 9 run is checked after push.

## Cost statement

No paid accounts, no paid CI minutes (public repo), no hosted database, no paid
UI kit, no marketplace action, no paid LLM API. Groq is strictly optional and
free-tier only; the default reporter is fully offline.

## Links

- [Build notes](BUILD_NOTES.md)
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
