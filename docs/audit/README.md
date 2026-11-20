# Live audit artifacts — 2026-11-20

These files are raw outputs from two real Kind/Chaos Mesh battles run during the
technical demonstration audit. They are kept separate from the committed demo
evidence in `ml/` so the dashboard and published numbers stay unchanged.

| File | Contents |
| --- | --- |
| `live_battle_2026-11-20.json` | First live run: 0.0 s detection, no recovery, 65/D/BLOCK, `restart · product-service · requested`, cleanup ok |
| `live_attack_2026-11-20.json` | Chaos Mesh attacker result for that run |
| `live_battle_2026-11-20.log` | Console output of `controller.cli evaluate` |
| `live_report_block_2026-11-20.md` | Template incident report generated from that artifact |
| `baseline_2026-11-20.log` | Output of the documented 40-sample baseline recalibration |
| `live_battle_recalibrated_2026-11-20.json` | Second live run after recalibration: not detected, 37.2 s recovery, 70/C/PROMOTE, cleanup ok |
| `live_attack_recalibrated_2026-11-20.json` | Chaos Mesh attacker result for that run |
| `live_battle_recalibrated_2026-11-20.log` | Console output of that battle |
| `live_report_recalibrated_2026-11-20.md` | Template incident report generated from that artifact |

See [DEMO_AUDIT.md](../DEMO_AUDIT.md) for the full audit and
[DEMO_RUNBOOK.md](../DEMO_RUNBOOK.md) for reproduction commands.
