# Phase 5 — LLM incident reporter

## What this phase adds

A reporter that turns the latest battle evidence into a clean Markdown incident
report with six fixed sections: **Summary, Timeline, Root cause, Actions taken,
Outcome, Follow-ups**.

It is offline by default. A deterministic template backend writes the report
from recorded facts only — no API key, no network call, no invented numbers.
A real model can be added through **Groq's free tier** (no card needed) by
setting `GROQ_API_KEY`. No paid API is used anywhere in this project.

## Files

| Path | Purpose |
|---|---|
| `reporter/incident.py` | Flat facts-only view of the latest battle |
| `reporter/prompt.py` | Prompt that says "use only these facts" |
| `reporter/sections.py` | The six required section names |
| `reporter/llm.py` | Offline template backend + free Groq backend |
| `reporter/report.py` | Generates and validates the report |
| `reporter/cli.py` | `python -m reporter.cli ...` |
| `controller/evidence.py` | New Phase 4 hook: saves `ml/last_battle.json` |
| `tests/test_phase5.py` | 15 tests |
| `docs/phase5.md` | This file |
| `Makefile` | `report`, `report-groq` |

## How it uses facts

The report is built from `ml/last_battle.json`, which the controller now writes
after every `evaluate` call. It contains the battle result, the score and the
gate decision. The reporter never invents a service, timestamp or number: the
template backend formats the values directly, and the LLM prompt explicitly
forbids fabrication.

Every generated report is validated: if any of the six headings is missing, the
reporter raises `ReporterError` instead of writing a partial report.

## Exact commands

```powershell
cd D:\Projects\1\chaosarena

# 1. Produce fresh evidence (do this once after any new battle)
.\.venv\Scripts\python.exe -m controller.cli evaluate `
  --attack network-latency --target payment-service `
  --duration 20 --settle 30 --version v1.0.3

# 2. Inspect what the reporter knows
.\.venv\Scripts\python.exe -m reporter.cli guard
.\.venv\Scripts\python.exe -m reporter.cli show
.\.venv\Scripts\python.exe -m reporter.cli prompt

# 3. Write the report (offline, default)
.\.venv\Scripts\python.exe -m reporter.cli report --backend template --out ml\incident_report.md

# 4. Optional, FREE real model: Groq free tier
#    Create a free key at https://console.groq.com/keys
$env:GROQ_API_KEY='gsk_your_free_key_here'
.\.venv\Scripts\python.exe -m reporter.cli report --backend groq --out ml\incident_report_groq.md
```

## Results actually measured on this laptop

- **64 tests pass** (48 earlier + 16 new).
- Fresh battle: detected at **14.0 s**, diagnosed `latency_spike` on
  `order-service` (`z=+289.5`), requested a restart for it, score **100**, verdict **PROMOTE**
  for `v1.0.3`.
- Offline report written to `ml/incident_report.md` with all six sections and
  the real numbers above.
- HTTP path verified end-to-end against a local OpenAI-compatible test server:
  the request went to `/v1/chat/completions` with the bearer token, and the
  returned Markdown passed section validation.
- Groq backend added with the **free** endpoint `https://api.groq.com/openai/v1/chat/completions`
  and free model `openai/gpt-oss-20b`; key, endpoint and model selection covered
  by tests. No paid API key is required or used.
- **Live Groq run verified:** a real free-tier call wrote `ml/incident_report_groq.md`
  with all six sections and the correct facts (`v1.0.3`, `network-latency`,
  `payment-service`, detected at `14.0 s`, `latency_spike` on `order-service`,
  `z=+289.5`, score `100`, grade `A`, `PROMOTE`).

## Common errors and fixes

| Error / surprise | Cause | Fix |
|---|---|---|
| `no battle evidence at ml/last_battle.json` | No battle has run since the hook was added | Run `controller.cli evaluate` once |
| `report is missing required sections` | LLM used `**Heading**` instead of `## Heading` | Fixed: validator accepts both; prompt now asks for `## Heading` explicitly. Use `--backend template` as fallback |
| `GROQ_API_KEY is not set` | `groq` backend selected without a free key | Create one at `console.groq.com/keys` and set `$env:GROQ_API_KEY` |
| `HTTP Error 403: Forbidden` from Groq | Default `Python-urllib` User-Agent was rejected | Fixed: the client now sends `User-Agent: chaosarena/1.0` |
| `429 Too Many Requests` from Groq | Free-tier rate limit reached | Wait a minute, or use `--backend template` |
| Curly quotes or dashes look odd in a terminal | Windows console encoding | Open the Markdown file in an editor |

## Why the offline backend matters

A demo must not fail because an API key is missing. The template backend gives
a complete, repeatable report on every machine, while the same interface lets
you swap in Groq's free model when you want a real LLM — still with no cost and
no change to the rest of the project.
