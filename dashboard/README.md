# ChaosArena Dashboard

A small React + Vite UI for the Phase 4 release gate, Phase 5 incident report and
v1.2 AI Reasoning panel. It uses plain CSS and free open-source packages only —
no UI kit, no cloud, and no API key is exposed to the browser.

## Run locally

Terminal 1 — start the gate API:

```powershell
# From the repository root
.\.venv\Scripts\python.exe -m uvicorn controller.api:app --host 127.0.0.1 --port 8080
```

Terminal 2 — start the UI:

```powershell
# From the repository root
cd dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173

## What it shows

- API health
- Latest gate verdict, score, grade, reasons and metadata
- Decision history from `ml/gate_decisions.jsonl`
- Incident report from `ml/incident_report.md`
- A form to run a real battle through `POST /gate/evaluate`, with an opt-in
  **AI battle** checkbox for fresh advisory notes
- The learned RL attacker policy from `GET /rl/policy` (read-only Q table)
- A small score trend and mini-bars drawn with plain CSS — no chart library
- Sidebar navigation, an always-visible key-results strip and a result toast
- A real battle timeline from `GET /evidence` with measured detection/recovery times
- Learned-vs-random and detector comparison panels, labelled offline — not live battles
- Search and PROMOTE/BLOCK filters in decision history
- Copy/download actions for the incident report
- An **AI Reasoning** section from `GET /ai/reasoning`: Groq's attack idea, Gemini's
  defence reading, the local DQN ranking and the report backend. It prefers fresh
  notes from `ml/deep/live/runtime/` after an **AI battle**, and otherwise shows the
  isolated committed v1.2 live-run evidence. No API keys are shown.

Full UI/evidence notes: `docs/DASHBOARD.md` and `docs/V12_LIVE_VALIDATION.md` in
the repository root.

Set `VITE_API_URL` if the API runs somewhere other than `http://127.0.0.1:8080`.

## Build

```powershell
npm run build
npm run preview
```
