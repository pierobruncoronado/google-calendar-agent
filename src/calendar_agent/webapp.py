"""Capa-2 web chat frontend for the Calendar agent (FastAPI). One page, vanilla
JS, no template engine or build step — the spec rules out an elaborate frontend."""

import sys
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from calendar_agent.auth import AuthError, get_calendar_service
from calendar_agent.conversation import handle_turn, new_session_state

load_dotenv()

app = FastAPI()
_sessions: dict[str, dict] = {}
_service = None


def _get_service():
    global _service
    if _service is None:
        _service = get_calendar_service()
    return _service


class ChatMessage(BaseModel):
    message: str


_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Agente de Google Calendar</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; }
  #log { border: 1px solid #ccc; border-radius: 8px; padding: 12px; height: 420px; overflow-y: auto; margin-bottom: 12px; }
  .msg { margin: 6px 0; }
  .user { text-align: right; color: #1a4; }
  .agent { text-align: left; color: #135; }
  form { display: flex; gap: 8px; }
  input { flex: 1; padding: 8px; }
  button { padding: 8px 16px; }
</style>
</head>
<body>
<h1>Agente de Google Calendar</h1>
<div id="log"></div>
<form id="form">
  <input id="input" autocomplete="off" placeholder="¿Qué tienes mañana?" />
  <button type="submit">Enviar</button>
</form>
<script>
const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('input');

function append(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  append('user', text);
  input.value = '';
  const res = await fetch('/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: text}),
  });
  const data = await res.json();
  append('agent', data.reply);
});
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE


@app.post("/chat")
def chat(payload: ChatMessage, request: Request, response: Response) -> dict:
    session_id = request.cookies.get("session_id") or str(uuid.uuid4())
    state = _sessions.setdefault(session_id, new_session_state())

    try:
        service = _get_service()
    except AuthError as exc:
        return {"reply": f"Error de autenticación: {exc}"}

    reply = handle_turn(service, state, payload.message)

    response.set_cookie("session_id", session_id, httponly=True)
    return {"reply": reply}


def main() -> None:
    try:
        _get_service()
    except AuthError as exc:
        print(f"Error de autenticación: {exc}", file=sys.stderr)
        raise SystemExit(1)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
