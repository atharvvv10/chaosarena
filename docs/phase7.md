# Phase 7 — React Dashboard

## What this phase adds

A small local React + Vite dashboard that reads the Phase 4 release gate and the
Phase 5 incident report, and can launch a real battle through the existing
`POST /gate/evaluate` endpoint. It uses plain CSS and free open-source packages
only. No UI kit, no backend-as-a-service, no API key, no cloud.

## Plan (executed)

1. Add read-only API routes for decision history and the latest report, and allow
   the Vite dev/preview origins through CORS.
2. Create `dashboard/` with React 19 + Vite 8, four panels, and one battle form.
3. Add Phase 7 acceptance tests (API, CORS, safety strings, free-package check).
4. Build the frontend, run both servers, and verify the live page in a browser.
5. Wire `npm ci && npm run build` into the free GitHub Actions workflow and push.

## Files created / changed

| Path | Purpose |
| --- | --- |
| `controller/gate.py` | `recent_decisions()` helper: newest-first JSONL history. |
| `controller/api.py` | CORS for `127.0.0.1:5173` / `4173`; `GET /gate/history`; `GET /report/latest`. |
| `dashboard/package.json` | Exact free dependencies: `react`, `react-dom`, `vite`, `@vitejs/plugin-react`. |
| `dashboard/package-lock.json` | Locked versions for reproducible `npm ci` in CI. |
| `dashboard/vite.config.js` | Local-only dev/preview host and ports. |
| `dashboard/index.html` | Vite entry document. |
| `dashboard/src/main.jsx` | React root with `StrictMode`. |
| `dashboard/src/api.js` | Thin fetch wrapper; base URL from `VITE_API_URL`. |
| `dashboard/src/App.jsx` | Gate card, battle form, history table, report panel. |
| `dashboard/src/styles.css` | Hand-written dark theme; no external fonts or CSS framework. |
| `dashboard/README.md` | Two-terminal run instructions and panel description. |
| `tests/test_phase7.py` | 7 acceptance tests. |
| `tests/test_phase6.py` | Workflow now also asserts the Node build step. |
| `.github/workflows/ci.yml` | Adds `setup-node@v7.1.0` and `npm ci && npm run build`. |
| `README.md` | Status and checklist updated to Phase 7. |
| `.gitignore` | Already ignores `node_modules/` and `dist/`. |

## Commands used

```powershell
# Backend + frontend tests
.\.venv\Scripts\python.exe -m pytest -q

# Frontend install + production build
cd D:\Projects\1\chaosarena\dashboard
npm install
npm run build

# Run locally (two terminals)
.\.venv\Scripts\python.exe -m uvicorn controller.api:app --host 127.0.0.1 --port 8080
cd D:\Projects\1\chaosarena\dashboard
npm run dev
```

Open <http://127.0.0.1:5173>.

## Verified results

- **84 tests pass** (9 Phase 6 + 7 Phase 7 + earlier 68).
- `npm run build`: 17 modules, `dist/assets/index-*.js` ≈ 227 kB (71 kB gzip),
  built in 243 ms. No vulnerabilities from `npm install`.
- Browser check: `API online`; gate card shows `PROMOTE / 100 / grade A`;
  history shows 4 real decisions; incident report text renders from
  `ml/incident_report.md`.
- Live UI battle: `network-latency` on `payment-service`, duration 10 s,
  settle 20 s, threshold 0 → **PROMOTE**, score 70 (grade C),
  `detected=false`, `recovered=true`, `cleanup=true`, `chaos_objects_remaining=0`.
  The new decision appeared at the top of the history table immediately.
- Network tab: all five API calls returned `200`; CORS preflight returned `200`.
- Console: only the React DevTools info message; no errors or warnings.

## Common errors and fixes

| Problem | Cause | Fix |
| --- | --- | --- |
| `Access to fetch blocked by CORS` | Vite origin not on the API allowlist | Added `5173` and `4173` for both `localhost` and `127.0.0.1` in `CORSMiddleware`. |
| `Cannot reach the gate API` | API not running on port 8080 | Start uvicorn in a separate terminal, or set `VITE_API_URL`. |
| Blank page after a dependency bump | Wrong React/Vite peer versions | Pinned exact versions in `package.json` and committed `package-lock.json`. |
| Duplicate requests in dev | React `StrictMode` double-invokes effects in development | Harmless; production build does not do this. |
| Battle button stuck on `Battling…` | Real attack + settle + verification takes ~40–60 s | Wait; the button re-enables when the API responds. |
| `npm ci` fails in CI | Missing lockfile | `dashboard/package-lock.json` is committed. |

## Why these choices

- The dashboard only calls the existing controller API; it never imports
  `attacker/` or `defender/`, so the Phase 3 isolation boundary stays intact.
- The battle button uses the same allowlisted endpoint the CLI uses, so the UI
  cannot bypass the `shop-test` safety rules.
- `VITE_API_URL` keeps the build portable without adding secrets or cloud config.
- Plain CSS and pinned free packages keep the frontend reproducible and bill-free.

## Cost check

React, Vite and the GitHub Actions runner are all free/open source. The workflow
uses only `ubuntu-latest` and public actions; no marketplace apps, no secrets,
no hosted UI services. The dashboard makes no external network calls.

## Phase 7 status

Complete locally and verified in a real browser. CI build verification is
included in the same free workflow as Phase 6; the GitHub run result is checked
after push.
