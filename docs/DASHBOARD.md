# Dashboard UI and evidence panels

The React dashboard is intentionally dependency-free: React, React DOM and Vite are the
only frontend packages. Everything shown here is rendered locally; there are no hosted
charts, no API keys and no external UI kits.

## Interface upgrade

- **Sticky section navigation** — Overview, Battle, Evidence and History jump to the
  matching card and highlight the section currently in view.
- **Key-results strip** — resilience score, detection time, recovery time and cleanup
  status are always visible without scrolling.
- **Release gate card** — score ring, verdict, reasons and the evaluated facts from the
  latest gate decision.
- **Battle form** — unchanged safety contract: allowlisted `shop-test` targets only,
  with the same five inputs and one attacker selector.
- **Battle timeline** — turns the committed `ml/last_battle.json` record into an ordered
  inject → symptom → repair request → recover → cleanup story with the measured timings.
  A `0.0 s` detection time is labelled "anomaly present on first poll after launch";
  the JSON carries the same clarification in `detection_basis`.
- **Recovery control** — compares the gated battle with a no-remediation run of the same
  fault and says plainly that two single runs are not a statistical study.
- **History tools** — search by version, attack, target or verdict, plus one-click
  PROMOTE/BLOCK filters.
- **Report actions** — copy the incident report to the clipboard or download it as Markdown.
- **Result toast** — confirms each battle's verdict and score without needing to scroll.

## New evidence API

`GET /evidence` returns four local files in one response:

| Field | Source | Label in the UI |
| --- | --- | --- |
| `last_battle` | `ml/last_battle.json` | Real battle timeline |
| `rl_benchmark` | `ml/rl_benchmark.json` | Learned vs random (offline seeded simulator) |
| `defender_benchmark` | `ml/defender_benchmark.json` | Detector comparison (offline seeded samples) |
| `no_defender_baseline` | `ml/no_defender_baseline.json` | Recovery control (real local run, no remediation) |

Missing or malformed files produce `null` for that field instead of breaking the page.
The UI labels the two benchmark panels as **offline** and **not a live battle**; only the
timeline and the recovery-control row are described as real local runs.

## Why this is honest

The dashboard does not claim that the benchmarks were produced by live chaos runs. The
learned-vs-random numbers come from 200 seeded simulator episodes. The detector numbers
come from 40 recorded normal samples plus 160 seeded fault injections. The headline
`network-latency` battle is the real detected run recorded in `ml/last_battle.json`;
its repair was requested but not proven necessary, because a separate no-Defender run
of the same fault recovered without any action.

## Verify locally

```bash
.venv\Scripts\python.exe scripts\verify_all.py
npm run dev --prefix dashboard
```

Then open `http://127.0.0.1:5173` with the gate API on `http://127.0.0.1:8080`.
