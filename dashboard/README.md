# ChaosArena Dashboard

A small React + Vite UI for the Phase 4 release gate and Phase 5 incident report.
It uses plain CSS and free open-source packages only — no UI kit, no cloud, no API key.

## Run locally

Terminal 1 — start the gate API:

```powershell
cd D:\Projects\1\chaosarena
.\.venv\Scripts\python.exe -m uvicorn controller.api:app --host 127.0.0.1 --port 8080
```

Terminal 2 — start the UI:

```powershell
cd D:\Projects\1\chaosarena\dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173

## What it shows

- API health
- Latest gate verdict, score, grade, reasons and metadata
- Decision history from `ml/gate_decisions.jsonl`
- Incident report from `ml/incident_report.md`
- A form to run a real battle through `POST /gate/evaluate`
- The learned RL attacker policy from `GET /rl/policy` (read-only Q table)
- A small score trend and mini-bars drawn with plain CSS — no chart library
- Sidebar navigation, an always-visible key-results strip and a result toast
- A real battle timeline from `GET /evidence` with measured detection/recovery times
- Learned-vs-random and detector comparison panels, labelled offline — not live battles
- Search and PROMOTE/BLOCK filters in decision history
- Copy/download actions for the incident report

Full UI/evidence notes: `docs/DASHBOARD.md` in the repository root.

Set `VITE_API_URL` if the API runs somewhere other than `http://127.0.0.1:8080`.

## Build

```powershell
npm run build
npm run preview
```
