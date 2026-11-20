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
  detect → diagnose → repair → recover → cleanup story with the measured timings.
- **History tools** — search by version, attack, target or verdict, plus one-click
  PROMOTE/BLOCK filters.
- **Report actions** — copy the incident report to the clipboard or download it as Markdown.
- **Result toast** — confirms each battle's verdict and score without needing to scroll.

## New evidence API

`GET /evidence` returns three local files in one response:

| Field | Source | Label in the UI |
| --- | --- | --- |
| `last_battle` | `ml/last_battle.json` | Real battle timeline |
| `rl_benchmark` | `ml/rl_benchmark.json` | Learned vs random (offline seeded simulator) |
| `defender_benchmark` | `ml/defender_benchmark.json` | Detector comparison (offline seeded samples) |

Missing or malformed files produce `null` for that field instead of breaking the page.
The UI labels the two benchmark panels as **offline** and **not a live battle**; only the
timeline is described as a real battle.

## Why this is honest

The dashboard does not claim that the benchmarks were produced by live chaos runs. The
learned-vs-random numbers come from 200 seeded simulator episodes. The detector numbers
come from 40 recorded normal samples plus 160 seeded fault injections. The headline
`network-latency` battle is the real detect-and-repair run recorded in `ml/last_battle.json`.

## Verify locally

```bash
.venv\Scripts\python.exe scripts\verify_all.py
npm run dev --prefix dashboard
```

Then open `http://127.0.0.1:5173` with the gate API on `http://127.0.0.1:8080`.
