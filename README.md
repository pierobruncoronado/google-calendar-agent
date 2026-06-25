# Agente conversacional de Google Calendar (v1)

Agente que entiende lenguaje natural y opera sobre tu Google Calendar real vía OAuth 2.0 y la
API oficial: consulta, crea, mueve y borra eventos, con confirmación humana (HITL) en las
acciones destructivas. Spec completo en `docs/spec-proyecto-google-calendar-agent.md`,
decisiones de implementación en `docs/DECISIONS.md`.

**Estado:** H1-H5 completos (OAuth, lectura, interpretación NL, escritura+HITL, manejo de
errores). Un frontend mostrable es capa 2, fuera de v1.

## Prerrequisitos

- Python 3.12 (no 3.14 — algunas dependencias todavía no tienen wheel). Si tu `python` por
  defecto es 3.14, crea el venv con `py -3.12 -m venv .venv`.
- Un proyecto en Google Cloud Console con:
  - Calendar API habilitada.
  - OAuth consent screen configurado (modo "Testing" alcanza para uso personal).
  - Credenciales OAuth tipo "Desktop app" descargadas como `credentials.json`.
- Una API key de Anthropic (`ANTHROPIC_API_KEY`) — la interpretación de lenguaje natural
  depende de ella.

## Instalación

```powershell
git clone https://github.com/pierobruncoronado/google-calendar-agent.git
cd google-calendar-agent
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

`requirements-dev.txt` incluye `requirements.txt` + `pytest`. Si solo vas a correr el agente
(sin tests), `pip install -r requirements.txt` alcanza.

## Configuración

1. Coloca el `credentials.json` descargado de Google Cloud Console en la raíz del proyecto.
2. Copia `.env.example` a `.env` y completa `ANTHROPIC_API_KEY`:

```powershell
Copy-Item .env.example .env
notepad .env
```

**No uses `Set-Content` ni `>` para editar `.env` en PowerShell** — escriben UTF-8 con BOM, lo
que rompe `python-dotenv` al leer el archivo (falla en silencio o carga la primera clave con el
nombre corrompido). Usa Notepad, o
`[System.IO.File]::WriteAllLines(ruta, lineas, (New-Object System.Text.UTF8Encoding $false))`
para forzar UTF-8 sin BOM.

## Primer uso (OAuth)

El proyecto usa layout `src/`, así que hay que apuntar `PYTHONPATH` a `src` para correr el
módulo directamente:

```powershell
$env:PYTHONPATH = "src"
python -m calendar_agent.main
```

La primera vez abre el navegador para el consent flow de Google y guarda el token en
`token.json` (gitignored). Las corridas siguientes refrescan el token automáticamente — no
vuelve a pedir login mientras `token.json` siga siendo válido.

## Uso

Lectura por rango:

```powershell
python -m calendar_agent.main "hoy"
python -m calendar_agent.main "mañana"
python -m calendar_agent.main "2026-06-30"
```

Lenguaje natural (cualquier otro texto se interpreta vía LLM):

```powershell
python -m calendar_agent.main "¿qué tengo el viernes?"
python -m calendar_agent.main "agéndame dentista jueves 3pm 1 hora"
python -m calendar_agent.main "mueve mi reunión de las 2 a las 4"
python -m calendar_agent.main "borra mi reunión de mañana a las 10"
```

Las acciones de escritura (crear/mover/borrar) siempre proponen la acción exacta y esperan
confirmación (`si`/`no`) antes de tocar el calendario. Si la fecha/hora es ambigua o no se
puede identificar el evento, el agente pide aclaración en vez de adivinar.

## Capa 2: interfaz web

Una alternativa al CLI: una página de chat mínima (FastAPI + HTML/JS vanilla, sin build step)
con conversación multi-turno — recuerda el turno anterior, así que la confirmación HITL y la
aclaración de ambigüedad funcionan como una conversación real, no como comandos sueltos.

```powershell
$env:PYTHONPATH = "src"
python -m calendar_agent.webapp
```

Abre `http://127.0.0.1:8000` en el navegador. Falla rápido (antes de levantar el servidor) si
el OAuth/credenciales no son válidos, igual que el CLI. El estado de la conversación vive en
memoria del proceso (cookie de sesión) — no hay base de datos en v1, así que se pierde si
reinicias el servidor.

## Tests

```powershell
python -m pytest
```

Todos los tests usan mocks — no hacen llamadas reales a Google ni a Anthropic, así que corren
sin `.env`/`credentials.json` válidos. `pytest.ini` ya apunta `pythonpath` a `src`, no hace
falta exportar `PYTHONPATH` para los tests (sí para correr el CLI directamente, ver arriba).

## Seguridad

`.env`, `token.json` y `credentials.json` están en `.gitignore` — nunca deberían aparecer en un
commit. Verifica con `git status` antes de cualquier commit si los tocaste manualmente.

## Estructura

```
src/calendar_agent/
  auth.py     # OAuth consent flow + refresh de tokens (H1)
  events.py   # lectura/escritura de eventos contra la API de Calendar (H2, H4) + manejo de errores (H5)
  intent.py        # extracción de intención NL vía forced tool-use de Anthropic (H3, H5)
  main.py          # entrypoint CLI: despacha lectura, escritura+HITL y aclaración de ambigüedad
  conversation.py  # lógica de turno multi-turno para la web UI (Capa 2), reutiliza events.py/intent.py
  webapp.py        # entrypoint FastAPI: una página de chat + sesión en memoria (Capa 2)
tests/        # tests mockeados, uno por módulo
docs/         # spec + registro de decisiones
```

## Fuera de alcance (v1)

Gmail, multi-usuario, frontend elaborado, recurrencia avanzada de eventos, notificaciones push
— ver `docs/spec-proyecto-google-calendar-agent.md` §2 para el detalle completo.
