# Conversational Google Calendar Agent (v1)

Agent that understands natural language and operates on your real Google Calendar via OAuth 2.0
and the official API: reads, creates, moves, and deletes events, with human confirmation (HITL)
on destructive actions. Full spec in `docs/spec-proyecto-google-calendar-agent.md`, implementation
decisions in `docs/DECISIONS.md`.

**Status:** H1–H6 + Layer 2 complete (OAuth, read, NL interpretation, write + HITL, error
handling, reproducible setup, minimal web UI). Full case study in `CASE_STUDY.md`.

## Prerequisites

- Python 3.12 (not 3.14 — some dependencies don't have wheels yet). If your default `python` is
  3.14, create the venv with `py -3.12 -m venv .venv`.
- A Google Cloud Console project with:
  - Calendar API enabled.
  - OAuth consent screen configured ("Testing" mode is enough for personal use).
  - OAuth credentials of type "Desktop app" downloaded as `credentials.json`.
- An Anthropic API key (`ANTHROPIC_API_KEY`) — natural language interpretation depends on it.

## Installation

```powershell
git clone https://github.com/pierobruncoronado/google-calendar-agent.git
cd google-calendar-agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt` + `pytest`. If you only want to run the agent
(no tests), `pip install -r requirements.txt` is enough.

## Configuration

1. Place the `credentials.json` downloaded from Google Cloud Console in the project root.
2. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`:

```powershell
Copy-Item .env.example .env
notepad .env
```

**Do not use `Set-Content` or `>` to edit `.env` in PowerShell** — they write UTF-8 with BOM,
which breaks `python-dotenv` when reading the file (fails silently or loads the first key with a
mangled name). Use Notepad, or
`[System.IO.File]::WriteAllLines(path, lines, (New-Object System.Text.UTF8Encoding $false))`
to force BOM-less UTF-8.

## First use (OAuth)

The project uses a `src/` layout, so you need to point `PYTHONPATH` to `src` to run the module
directly:

```powershell
$env:PYTHONPATH = "src"
python -m calendar_agent.main
```

The first run opens the browser for Google's consent flow and saves the token in `token.json`
(gitignored). Subsequent runs refresh the token automatically — no re-login as long as
`token.json` remains valid.

## Usage

Read by range:

```powershell
python -m calendar_agent.main "hoy"
python -m calendar_agent.main "mañana"
python -m calendar_agent.main "2026-06-30"
```

Natural language (any other text is interpreted via LLM):

```powershell
python -m calendar_agent.main "¿qué tengo el viernes?"
python -m calendar_agent.main "agéndame dentista jueves 3pm 1 hora"
python -m calendar_agent.main "mueve mi reunión de las 2 a las 4"
python -m calendar_agent.main "borra mi reunión de mañana a las 10"
```

Write operations (create / move / delete) always propose the exact action and wait for
confirmation (`si`/`no`) before touching the calendar. If the date/time is ambiguous or the
event cannot be identified, the agent asks for clarification instead of guessing.

## Layer 2: Web interface

An alternative to the CLI: a minimal chat page (FastAPI + vanilla HTML/JS, no build step) with
multi-turn conversation — remembers the previous turn, so HITL confirmation and ambiguity
clarification work as a real conversation, not standalone commands.

```powershell
$env:PYTHONPATH = "src"
python -m calendar_agent.webapp
```

Open `http://127.0.0.1:8000` in the browser. Fails fast (before starting the server) if the
OAuth credentials are invalid, same as the CLI. Conversation state lives in process memory
(session cookie) — no database in v1, so it is lost if you restart the server.

## Tests

```powershell
python -m pytest
```

All tests use mocks — no real calls to Google or Anthropic, so they run without valid
`.env`/`credentials.json`. `pytest.ini` already points `pythonpath` to `src`; no need to export
`PYTHONPATH` for tests (you do need it to run the CLI directly, see above).

## Security

`.env`, `token.json`, and `credentials.json` are in `.gitignore` — they should never appear in a
commit. Check with `git status` before any commit if you touched them manually.

## Structure

```
src/calendar_agent/
  auth.py          # OAuth consent flow + token refresh (H1)
  events.py        # Read/write events against the Calendar API (H2, H4) + error handling (H5)
  intent.py        # NL intent extraction via Anthropic forced tool-use (H3, H5)
  main.py          # CLI entrypoint: dispatches reads, write + HITL, and ambiguity clarification
  conversation.py  # Multi-turn logic for the web UI (Layer 2), reuses events.py/intent.py
  webapp.py        # FastAPI entrypoint: one chat page + in-memory session (Layer 2)
tests/             # Mocked tests, one per module
docs/              # Spec + decision log
```

## Out of scope (v1)

Gmail, multi-user, elaborate frontend, advanced event recurrence, push notifications — see
`docs/spec-proyecto-google-calendar-agent.md` §2 for the full details.
