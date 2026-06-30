# Conversational Google Calendar Agent

**NL → OAuth 2.0 → real Calendar API: the integration wall in practice — real auth bugs, UTC
offset surprises, and HITL on destructive writes.**

**Stack:** Python 3.12 · Anthropic SDK (`claude-haiku-4-5-20251001`) · google-api-python-client ·
google-auth-oauthlib · FastAPI (Layer 2 web UI) ·
[github.com/pierobruncoronado/google-calendar-agent](https://github.com/pierobruncoronado/google-calendar-agent)

---

## Metrics

| Metric | Value |
|---|---|
| Test suite | 68 / 68 passing (all mocked — runs without credentials) |
| Live integration bugs caught by milestone verification | 4 (all fixed before milestone close) |
| Milestones verified against real Calendar + Anthropic APIs | 7 of 7 (H1–H6 + Layer 2) |
| OAuth consent flows required by the end user | 1 (auto-refresh on every subsequent run) |
| Token cost per intent extraction | Logged per call (`intent_extraction_tokens` in JSON); no session aggregate |

---

## The Problem

This portfolio's prior projects — a clinic WhatsApp agent, a SQL analyst, and an LLM gateway —
are self-contained: they call external APIs, but they don't authenticate *as* the user, act on
the user's persistent data, or handle the lifecycle of OAuth tokens. The gap is the integration
wall: real OAuth flows, refresh-token expiry, API-layer errors the vendor documentation doesn't
cover, and destructive actions that must not run without human sign-off.

Google Calendar is a deliberate choice of target: widely deployed, well-documented, and full of
undocumented surface area that only shows up when you point real user data at it.

---

## What I Built

Five core behaviors, each verified against the real Google Calendar and Anthropic APIs:

1. **OAuth 2.0 consent + silent auto-refresh** (`src/calendar_agent/auth.py`): first run opens
   the browser for Google's consent flow and persists `token.json` (gitignored). Every run after
   that refreshes the access token silently — no re-authentication as long as the refresh token is
   valid.

2. **NL intent extraction via forced tool-use** (`src/calendar_agent/intent.py`): Haiku extracts
   structured intent + parameters using `tool_choice={"type": "any"}` over 5 tools
   (`read_events`, `create_event`, `move_event`, `delete_event`, `request_clarification`). No
   free-text parsing — if the model doesn't call one of the five, the call fails hard rather than
   returning ambiguous text.

3. **HITL on all writes** (`src/calendar_agent/main.py`, `src/calendar_agent/conversation.py`):
   create / move / delete always proposes the exact action with its resolved parameters (title,
   date, time) and waits for explicit confirmation. Any non-confirmation cancels with zero API
   calls made.

4. **LLM-based event identification** (`src/calendar_agent/events.py:_match_event_llm`): instead
   of using Google's `q=` text-search parameter, the agent fetches all events in a 30-day window
   and calls Haiku with forced tool-use to identify which event matches the user's description.
   Handles NL variation that a literal string match misses.

5. **Multi-candidate ambiguity gate**: when `_match_event_llm` finds more than one plausible
   match, it raises `AmbiguousEventError`, the agent lists the candidates, and no destructive
   action runs until the user selects one explicitly.

**Scope out (v1):** Gmail, multi-user, cloud deploy, complex recurrence rules (RRULE), push
notifications — all explicit in `docs/spec.md` §2.

---

## Architecture

```
User
 │
 ├── CLI  (calendar_agent.main)
 │     ├── auth.py           OAuth consent + token.json auto-refresh
 │     ├── intent.py         Haiku / tool_choice:any → {intent, params}
 │     └── events.py         Calendar API — list / insert / patch / delete
 │               └── _match_event_llm()   LLM identifies event by NL description
 │
 └── Web UI  (calendar_agent.webapp)   FastAPI + vanilla HTML/JS, Layer 2
               └── conversation.py    Multi-turn state: pending_confirmation / pending_clarification
```

Single-user, single-process. No cloud deploy: v1 is a CLI (`python -m calendar_agent.main`) with
a Layer 2 local web server (`python -m calendar_agent.webapp`, session-in-memory). `pytest.ini`
configures the `src/` layout; all 68 tests mock both Google Calendar and Anthropic — they run
without credentials.

---

## Results

The four live-verification bugs below are the project's central story. Each was caught by the
"verify against real APIs before closing the milestone" discipline — not in tests, and not by
reading the documentation more carefully.

**403 `accessNotConfigured` — OAuth scope and API enablement are independent gates (H2).**
The first live run returned `HttpError 403 accessNotConfigured`. The OAuth consent screen was
set up and `credentials.json` was valid. What wasn't done was enabling the Calendar API service
itself in the Google Cloud Console — a separate, project-level toggle, independent of the OAuth
consent configuration. The code behaved correctly: `CalendarError` propagated to a clear stderr
message and exit 1. But the lesson is architectural: OAuth scope grants the user's permission to
delegate access; API enablement grants the project permission to use the service. They're
different gates, both required, and failing to do both at setup means the first real API call
fails at runtime rather than at configuration time.

**UTC offset — Google returns UTC regardless of what you sent (H4).**
An event created for 10:00 AM local appeared as 15:00 when read back. The Calendar API always
serializes `start.dateTime` as UTC (with a `Z` suffix) in responses, regardless of the timezone
offset used in the create request. The H2 code (`_format_event_line`) parsed and displayed that
UTC string directly as local time — a silent bug that was never triggered in H2's live test
because that milestone returned "no events" (no formatted times to display). Fixed by adding
`LOCAL_TIMEZONE = "America/Lima"` in `events.py` and explicit `zoneinfo.ZoneInfo` conversion
in `_local_time()` (`tzdata>=2024.1` added to `requirements.txt` for Windows, where the
IANA database isn't shipped with the OS). The lesson: live verification against an empty result
doesn't exercise the formatting path; any milestone touching timestamps needs at least one live
event with a real time.

**`<UNKNOWN>` fill-in — required schema fields invite hallucinated values (Layer 2).**
The `move_event` tool schema (built in H3) had `nueva_fecha` and `nueva_hora` as required. When
testing multi-turn with "muévelo al jueves" (date only, no new time), Haiku filled `nueva_hora`
with the literal string `"<UNKNOWN>"`, producing a proposed action of "a 2026-07-02 <UNKNOWN>"
— a violation of the "proposes the exact action" acceptance criterion. The case was never
exercised in H3/H4 testing because those runs always provided both a date and a time. Fixed by
making both fields optional with an explicit system-prompt instruction not to invent fill-in
values; `move_event()` defaults to the original event's date or time for any omitted field.
Schema fields marked `required` invite a model that must produce a valid JSON object to fill
them with something — specifying `"do not invent"` in the description doesn't remove the
incentive as reliably as making the field optional does.

**`q=` literal match misses NL variation — the event-identification gap (H5 fix).**
`find_event_by_description` used Google's `q=` parameter, which runs a text search against event
titles. When the user says "cancela el café de mañana", `extract_intent` correctly extracts
`descripcion_evento: "café de mañana"` — but the Calendar API's `q=` search returns no match for
an event titled "Café con Vania": the word "mañana" isn't in the title. The unit tests validated
the implementation against itself (the mock returned the event for any `q=`), not against real
user language. Fixed by removing `q=` and replacing with `_match_event_llm`: fetch all events in
the relevant window (`maxResults=20`), then call Haiku to identify the right one. The spec's
EARS criterion — "shall not do string-literal match" — was added in a later revision after the
gap was discovered in live use; testing against the original implementation didn't surface it
until a realistic user phrase was tried.

---

## Key Decisions & Trade-offs

- **OAuth scope: full `calendar` (not narrower `calendar.events`)** — single consent flow covers
  all operations from H1 through Layer 2. Trade-off: broader than the minimum required; acceptable
  because v1 runs in Google Cloud Console "Testing" mode with one developer account — the blast
  radius is the developer's own calendar.

- **`tool_choice: any` for intent extraction** — forces exactly one tool call per turn; no
  ambiguous free-text output path. Trade-off: if the model produces no `tool_use` block
  (which shouldn't happen with `any`), the call raises `IntentError` rather than degrading
  gracefully — the failure is explicit, not silent.

- **LLM for event identification (not `q=`)** — handles NL variation, partial titles, participant
  names. Trade-off: one extra Haiku call per `move_event`/`delete_event`, adding latency and
  token cost to every destructive write.

- **Multi-turn HITL via two HTTP requests (Layer 2)** — confirmation arrives in the next request,
  not by blocking the current one. `conversation.py` holds `pending_confirmation` state in the
  server process. Trade-off: state is lost on server restart (no DB in v1), documented in the
  README and spec §6.

- **In-memory session, no DB** — zero infrastructure dependency for v1. Trade-off: not viable for
  multi-user or production; explicitly scoped out in `docs/spec.md` §2.

---

## What's Next (v2)

- Cloud deploy: Docker + Railway (same pattern as the clinic agent and SQL analyst)
- Multi-user support: replace the in-memory session dict with DB-backed storage
- Gmail integration: explicitly reserved for v2 in spec §2
- Complex recurrence rules (RRULE)
- Per-session token and cost aggregate reporting

---

## Honest Scope Note

Portfolio project, single developer account. No cloud deploy, no public URL. All 68 tests mock
both the Google Calendar and Anthropic APIs — they pass without credentials. Live verification
was done against the developer's personal Google Calendar. The OAuth consent screen runs in
"Testing" mode in Google Cloud Console, which limits the app to pre-registered test users (the
developer themselves).
