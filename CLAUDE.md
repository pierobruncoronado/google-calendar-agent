# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Pre-implementation.** This repository currently contains only the spec document at
`docs/spec-proyecto-google-calendar-agent.md` — no code, no README, no `DECISIONS.md` yet.
There are no build/lint/test commands to run because nothing has been scaffolded. When you
start implementing, follow the stack choices below and create `docs/DECISIONS.md` for new
decisions (per §8 of the spec) rather than inventing your own structure.

The spec is the source of truth. Read it in full before doing any work — it contains binding
EARS-style acceptance criteria (§5) and decisions marked "NO re-litigar" (§4). Treat those as
fixed unless the user explicitly reopens them.

## What this project is

A conversational agent that operates on the user's real Google Calendar via OAuth 2.0 and the
official Calendar API. The point of the project (per spec §1) is to cross the "integration
wall" — real OAuth, refresh tokens, rate limits, and HITL on destructive actions — not to build
another self-contained demo agent.

## Binding decisions (do not re-litigate — spec §4)

- v1 = Calendar only. Gmail is explicitly v2 — do not touch Gmail APIs in v1.
- This is an **agent** (LLM decides and acts via tool-use), not cron/scripted automation.
- Human-in-the-loop (HITL) confirmation is required **only** for destructive writes
  (create/move/delete). Reads never require confirmation.
- Single user (the developer's own account) in v1. No multi-account/multi-tenant logic.
- Build the integration core first. A presentable frontend is an explicit "layer 2," added only
  after H1–H6 (see milestones below) are done — do not start UI work before that.

## Out of scope for v1 (spec §2)

Do not implement these unless the user explicitly expands scope:
- Gmail integration.
- Multi-user / multi-account support.
- An elaborate frontend (CLI or minimal interface is sufficient for v1).
- Complex recurrence rules (advanced RRULE).
- Push notifications / real-time sync.

## Stack (spec §3)

- Python 3.12 — **not 3.14** (psycopg2 wheel availability if a DB is introduced).
- CLI for v1; FastAPI only if/when exposed as a service.
- Anthropic SDK for the LLM. Default model: **Haiku** (intent interpretation is a simple task) —
  only escalate to a larger model if evals show parameter-extraction failures.
- `google-api-python-client` + `google-auth-oauthlib` for Calendar access.
- Structured output for parameter extraction (date/time/title) via **forced tool-use**, never
  free-text parsing of LLM output.

### Windows gotchas (critical — this project's secrets live in `.env`)

- PowerShell's `Set-Content` and `>` redirection write UTF-8 **with BOM**, which breaks
  `python-dotenv` when it reads `.env` (silently fails to load vars, or loads the first key with
  a mangled name). Never create/edit `.env` with `>` or `Set-Content`. Use Notepad, or
  PowerShell's `[System.IO.File]::WriteAllLines(path, lines, (New-Object
  System.Text.UTF8Encoding $false))` to force BOM-less UTF-8.
- Run tests as `python -m pytest`, not bare `pytest` — avoids picking up the wrong interpreter/
  environment on Windows.

## Security (spec §3 — critical for this project)

- OAuth tokens and client secrets live only in `.env` / a secure store — never in code or logs.
- Before the **first commit**, verify `.gitignore` excludes `.env`, `token.json`, and
  `credentials.json`. This project's stated theme is "credential exposure is the failure mode
  to design against," so treat this as a hard gate, not a suggestion.
- Refresh tokens automatically; never force re-authentication on an expired access token.

## Acceptance criteria (spec §5) drive evals (spec §7)

Every EARS criterion in §5 has a corresponding eval in §7. When implementing a milestone, write
the eval for its criteria first (baseline), then implement against it — don't declare a
milestone done without running its eval. Key behaviors to preserve:
- Reads never invent events: an empty range must say so explicitly.
- Destructive writes (create/move/delete) always propose the exact action and wait for explicit
  confirmation before calling the API; a "no" or non-confirmation cancels with no API call.
- 429 responses get retried with backoff, never a crash.
- Permission errors / nonexistent-event errors are reported in clear language, never silently
  swallowed.
- Ambiguous date/time references ("el jueves" with no clear referent) trigger a clarification
  question instead of an assumed interpretation.

## Milestones (spec §6)

Implement in order — each is a verifiable gate, not a checkbox:
1. **H1 OAuth** — consent flow + token save/refresh. Verify: second run doesn't re-prompt login.
2. **H2 Read** — query events by range. Verify: real calendar data returned for "¿qué tengo mañana?".
3. **H3 NL interpretation** — LLM extracts intent + params via tool-use. Verify: extraction evals pass.
4. **H4 Write + HITL** — create/move/delete with confirmation gate. Verify: proposes → waits → executes only after explicit OK.
5. **H5 Errors** — backoff on 429, clear messages on permission/not-found/ambiguity. Verify: error-case evals pass.
6. **H6 Deploy + reproducible README.** Verify: runs from a clean checkout following the README.
7. **(Layer 2, after the core)** — minimal presentable frontend.

## Lifecycle (spec §8)

When something changes (bug or feature), edit the spec first, then the code. Log new decisions
in `docs/DECISIONS.md` (create it if it doesn't exist yet).
