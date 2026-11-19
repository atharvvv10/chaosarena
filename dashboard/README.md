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

Set `VITE_API_URL` if the API runs somewhere other than `http://127.0.0.1:8080`.

## Build

```powershell
npm run build
npm run preview
```
