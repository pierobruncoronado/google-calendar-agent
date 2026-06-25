# Decisiones de proyecto

Registro de decisiones no fijadas textualmente en el spec, tomadas durante la implementación.

## H1 — Scope de OAuth

**Decisión:** pedir `https://www.googleapis.com/auth/calendar` (lectura/escritura completa de calendarios y eventos), no `calendar.events` ni una variante read-only.

**Por qué:** el spec (§2, §5) requiere tanto lectura (H2) como escritura — crear/mover/borrar (H4) — en v1. Pedir un scope read-only obligaría a un segundo consent flow cuando llegue H4. `calendar.events` es una alternativa más estrecha (solo eventos, no metadata de calendarios) y sería defendible, pero la app se queda en estado "Testing" en Google Cloud Console con un solo test user (el propio desarrollador), por lo que el costo de seguridad del scope más amplio es marginal en este contexto. Se prefiere fijar el scope una sola vez.

**Fecha:** 2026-06-23 (H1).

## H1 — Cierre retroactivo del hito

**Decisión:** aplicar retroactivamente la regla "Cierre de hito" (agregada al CLAUDE.md global el 2026-06-24) a H1, que se había dado por cerrado antes de que la regla existiera.

**Verificación en vivo ejecutada (2026-06-24):**
- `PYTHONPATH=src python -m calendar_agent.main` con `token.json` ya existente de una corrida previa → no abrió el consent flow (sin browser, sin `run_local_server`), imprimió "Autenticación exitosa", exit code 0. Cumple el criterio EARS de §5: "el access token expirado se refresca automáticamente Y no se re-pide login al usuario" (o, en este caso, el token seguía válido y no requirió refresh — ambas ramas evitan re-autenticación).
- `python -m pytest -q` → 6/6 tests pasan (cubren: token válido sin flow, refresh sin flow, fallback a flow si no hay token, fallback a flow si el refresh falla, `AuthError` si falta `credentials.json`, `AuthError` si falla el guardado del token).

**Aprendizaje:** el spec y el código ya estaban correctos para H1 (commit `e8fa5c5`), pero el cierre no había incluido una verificación en vivo explícita ni un registro del cierre en sí — solo el commit de implementación. La regla de cierre de hito existe para que verificar-en-vivo no sea opcional ni implícito en el commit de feature, sino un paso separado y registrado.

**Fecha:** 2026-06-24.

## H1 — Formato y ubicación del token OAuth

**Decisión:** persistir las credenciales del usuario en `token.json`, un archivo standalone gitignored en la raíz del proyecto — no dentro de `.env`.

**Por qué:** `google-auth-oauthlib` serializa las credenciales como JSON (`Credentials.to_json()`), no como un valor de una sola línea. Forzar ese JSON dentro de `.env` requeriría escapar/comprimir el blob a una línea, lo cual es frágil y choca con el bug de BOM de PowerShell (`Set-Content`/`>`) ya documentado en `CLAUDE.md`. Un archivo JSON dedicado respeta el patrón nativo de la librería y sigue cumpliendo la regla de seguridad del spec ("`.env` / store seguro") — ambos son archivos locales fuera de git.

**Fecha:** 2026-06-23 (H1).

## H2 — Cierre del hito con verificación en vivo

**Decisión:** cerrar H2 (lectura de eventos por rango) tras conectar `events.py` al entrypoint de `main.py` (modo CLI opcional: `hoy` / `mañana` / fecha `YYYY-MM-DD`) y verificar en vivo contra el calendario real.

**Verificación en vivo ejecutada (2026-06-24):**
- Primer intento con `PYTHONPATH=src python -m calendar_agent.main "mañana"` → `HttpError 403 accessNotConfigured`. La API de Google Calendar no estaba habilitada en el proyecto de Google Cloud asociado a `credentials.json`. El código lo manejó correctamente: `list_events` lo envolvió en `CalendarError`, `main.py` imprimió un mensaje claro en stderr y salió con código 1, sin crash. El usuario habilitó la API en Cloud Console.
- Segundo intento, mismo comando → `"No tienes eventos programados mañana."`, exit code 0. Verificado a nivel de bytes (`ma\xf1ana` en cp1252) que el texto es correcto — el carácter `�` que aparece en algunas terminales es un artefacto de renderizado del entorno, no un bug de encoding en el código.
- Cumple el EARS de §5: "consultar la API y devolver los eventos en lenguaje natural" (consultó la API real) Y "cuando no hay eventos en el rango, decirlo explícitamente y no inventar" (el resultado real fue 0 eventos, reportado sin inventar nada).
- `PYTHONPATH=src python -m pytest -q` → 15/15 tests pasan (6 de H1 + 9 de H2, todos mockeados, sin llamadas reales a la API).

**Aprendizaje:** habilitar el scope OAuth (H1) no habilita la API en sí — son dos gates independientes en Google Cloud Console (OAuth consent + API enablement). Un 403 `accessNotConfigured` en cualquier llamada futura a una API nueva de Google debe hacer sospechar primero de este gate, no del código.

**Fecha:** 2026-06-24 (H2).

## H3 — Hueco de spec detectado: ANTHROPIC_API_KEY no declarado como lead-time externo

**Decisión:** agregar `ANTHROPIC_API_KEY` a §3 (Restricciones/NFRs) y al checklist de estrés (§8) del spec como dependencia externa con lead-time, al mismo nivel que `credentials.json`/OAuth consent screen de Google.

**Por qué:** al arrancar H3 (interpretación NL vía tool-use de la API de Anthropic) se detectó que no existe `.env` en el proyecto y que el spec original (Fase 1, checklist de estrés §8) solo marcaba como lead-time externo el setup de Google Cloud Console — nunca mencionó la API key de Anthropic, pese a que el stack (§3) ya declaraba "Anthropic SDK para el LLM" desde el principio. Es un hueco de completitud del spec: una dependencia externa bloqueante que no fue identificada en la fase de diseño, solo se hizo visible al tocar el código que la necesita.

**Aprendizaje:** el checklist de estrés de §8 se llenó mirando solo la integración más obvia (Google OAuth) y no se generalizó la pregunta "¿qué credenciales/lead-time externo necesita CADA hito, no solo el primero?". Para futuros proyectos con múltiples integraciones externas, revisar lead-time por hito, no solo una vez al congelar el spec.

**Fecha:** 2026-06-24 (detectado al arrancar H3, antes de escribir código).

## H3 — Alcance de los 4 intents y cierre del hito

**Decisión:** el tool-schema de extracción NL (`src/calendar_agent/intent.py`) define las 4 operaciones del spec (`read_events`, `create_event`, `move_event`, `delete_event`) con `tool_choice={"type": "any"}` forzando al modelo a llamar exactamente una. `main.py` conecta `read_events` a la lectura real (reusa `list_events`/`format_events_natural_language` de H2, sin confirmación, como exige §5). Para los 3 intents de escritura, `main.py` solo imprime la acción propuesta extraída (sin ejecutar contra la API) — la ejecución real + HITL es H4, no H3. Ambigüedad de fecha ("el jueves" sin contexto claro) queda explícitamente fuera de H3 y se implementará en H5, según el desglose del spec.

**Por qué:** diseñar los 4 schemas ahora evita rediseñar la extracción en H4 (los 3 ejemplos de NL de escritura ya están en §1 del spec), pero ejecutar solo lectura respeta el límite real del hito (H3 = extracción, H4 = escritura+HITL) sin sobre-alcance.

**Verificación en vivo ejecutada (2026-06-24):**
- Llamada real a la API de Anthropic (modelo `claude-haiku-4-5-20251001`) con el caso de eval exacto del spec §7: `"agéndame dentista jueves 3pm 1 hora"` con `today=2026-06-24` (miércoles) → `{"intent": "create_event", "params": {"titulo": "Dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}}`. Coincide con el resultado esperado del spec (fecha resuelta correctamente al próximo jueves).
- 3 casos adicionales verificados en vivo: lectura (`"¿qué tengo el viernes?"` → rango correcto), mover (`"mueve mi reunión de las 2 a las 4"`) y borrar (`"borra mi reunión de mañana a las 10"`) — los 4 intents extraen correctamente.
- CLI end-to-end (`PYTHONPATH=src python -m calendar_agent.main "<texto libre>"`) verificado contra el calendario real: la rama de lectura devuelve eventos reales (o "no tienes eventos", sin inventar); la rama de escritura imprime la propuesta sin tocar la API.
- Costo medido: cada llamada loguea `intent_extraction_tokens` (input/output tokens) en JSON, cumpliendo el eval de costo de §7.
- `python -m pytest -q` → 23/23 tests pasan (15 previos + 8 nuevos de `test_intent.py`, todos mockeados, sin llamadas reales a la API).

**Aprendizaje:** el caracter `�` visible en la consola de Windows al imprimir texto con tildes es el mismo artefacto de renderizado de terminal documentado en el cierre de H2 (cp1252), no un bug de encoding en el código ni en la respuesta del modelo.

**Fecha:** 2026-06-24 (H3).

## H4 — Resolución de evento por descripción libre (move/delete)

**Decisión:** para `move_event`/`delete_event`, donde la extracción NL (H3) solo da una `descripcion_evento` en texto libre (no un ID), se busca con `events().list(q=descripcion, timeMin=ahora, timeMax=ahora+30d)` y se toma el primer resultado (el más próximo en el tiempo) como candidato. Si no hay match, se reporta error sin pedir confirmación (nada que confirmar). Si hay match, se propone ESE evento específico (con su título/hora real) en el paso HITL — si es el equivocado, el usuario dice "no" y no se modifica nada.

**Por qué:** resolver ambigüedad entre múltiples matches (pedir aclaración explícita al usuario) es comportamiento de H5 según ya quedado registrado en el cierre de H3. Para H4, mostrar el evento específico encontrado en la confirmación ya cumple el EARS de §5 ("propone la acción exacta... espera confirmación") porque el usuario ve el detalle real antes de aprobar.

**Fecha:** 2026-06-24 (H4).

## H4 — Bug de zona horaria descubierto en verificación en vivo: la API de Calendar siempre devuelve `dateTime` en UTC

**Decisión:** agregar una constante `LOCAL_TIMEZONE = "America/Lima"` en `events.py` y convertir explícitamente con `zoneinfo.ZoneInfo` antes de mostrar cualquier hora al usuario (`_local_time()`, usado por `_format_event_line` y `describe_event`). Se agregó `tzdata>=2024.1` a `requirements.txt` porque Windows no trae la base de datos IANA y `zoneinfo` la necesita ahí.

**Por qué:** la verificación en vivo de H4 (crear → leer) mostró un evento creado para las 10:00 apareciendo como las 15:00 al leerlo de vuelta. Se inspeccionó el JSON crudo devuelto por la API y se confirmó que Google Calendar siempre serializa `start.dateTime`/`end.dateTime` en UTC (sufijo `Z`), sin importar qué offset se envió al crear — el campo `timeZone` es metadata para cálculos de recurrencia, no afecta el formato de `dateTime` en la respuesta. El código de H2 (`_format_event_line`) y el nuevo `describe_event` de H4 parseaban ese `dateTime` y mostraban la hora cruda asumiendo que ya estaba en hora local, sin convertir — funcionaba por casualidad en H2 porque la única verificación en vivo de ese hito fue contra un rango vacío (sin eventos con hora), así que el bug nunca se ejercitó hasta H4.

**Aprendizaje:** un EARS de §5 ("propone la acción exacta") es más estricto que "no crashea" — requiere que el dato mostrado al usuario sea correcto, no solo que la llamada a la API tenga éxito. Verificar en vivo con datos vacíos (como hizo H2) no prueba el camino de formateo de fecha/hora; cualquier verificación en vivo futura que toque horarios reales debe incluir al menos un evento con hora explícita, no solo el caso "no hay eventos".

**Fecha:** 2026-06-24 (H4, detectado en verificación en vivo, corregido antes de cerrar el hito).

## H5 — Manejo de errores: retry/backoff, mensajes claros y aclaración de ambigüedad

**Decisión:** se implementan las 3 piezas del hito en `events.py`/`intent.py`/`main.py`:
- `_execute_with_retry()` envuelve las 5 llamadas a la API de Calendar (`list`, `insert`, `get`, `patch`, `delete`); reintenta con backoff exponencial (1s, 2s) solo en `429`, hasta 3 intentos, y propaga cualquier otro error o el 429 agotado.
- `_calendar_error_message()` mapea `403` → "no tienes permiso para {acción}", `404` → "el evento no existe (puede haber sido borrado)", `429` agotado → mensaje de rate-limit, y deja el fallback genérico con el código HTTP para el resto.
- Se agregó una 5ª tool `request_clarification` (`pregunta: string`) a `intent.py`, con el system prompt instruyendo al modelo a usarla cuando no pueda identificar el evento a mover/borrar (sin descripción) o cuando la fecha/hora sigue siendo ambigua tras la regla determinista de H3. `main.py` la despacha imprimiendo la pregunta, sin tocar la API ni pedir confirmación.

**Verificación en vivo ejecutada (2026-06-25):**
- `429` y `403` (permisos) **no se verificaron en vivo** — provocar un rate-limit real o un error de permisos real contra la cuenta real del desarrollador es invasivo y no reproducible de forma segura/determinista. Se cubren solo con tests mockeados (`HttpError` simulado), incluyendo el caso de éxito tras 2 reintentos y el caso de agotar los 3 intentos.
- `404` sí se verificó en vivo: `delete_event(service, "evento-id-que-no-existe-12345")` contra la API real de Calendar → `CalendarError("No se pudo borrar el evento: el evento no existe (puede haber sido borrado).")`.
- Ambigüedad sí se verificó en vivo contra la API real de Anthropic: `"muévelo al jueves"` (sin descripción del evento) → el modelo llamó `request_clarification` y el CLI imprimió la pregunta sin tocar el calendario. Como regression check, `"agéndame dentista jueves 3pm 1 hora"` (caso claro de H3) siguió extrayendo `create_event` normalmente, confirmando que el nuevo tool/prompt no degradó el caso no-ambiguo.
- `python -m pytest` → 49/49 tests pasan (42 previos + 7 nuevos de H5: 3 de retry/backoff, 2 de mensajes claros 403/404, 1 de extracción de `request_clarification`, 1 de su despacho en `main.py`).

**Aprendizaje:** no todo EARS de error es igualmente verificable en vivo de forma segura — para casos donde reproducir la condición real es invasivo (rate limit, permisos), el test mockeado es la verificación primaria y corresponde decirlo explícitamente en el cierre del hito, no fingir una verificación en vivo que no ocurrió.

**Fecha:** 2026-06-25 (H5).

## H6 — Alcance de "Deploy" y verificación de reproducibilidad

**Decisión:** "Deploy" en H6 se interpreta como reproducibilidad de setup (README), no infraestructura de hosting — el spec (§3) condiciona FastAPI/servicio a "si se expone como servicio", y v1 es explícitamente CLI. No se agregó Docker, CI ni hosting; eso no está pedido por ningún EARS de §5 y sería alcance no solicitado.

**Verificación en vivo ejecutada (2026-06-25):**
- Clone local real (`git clone` del repo a un directorio temporal) → confirmado que el checkout queda limpio: sin `.venv`, `.env`, `credentials.json` ni `token.json` (los 4 correctamente gitignored).
- Siguiendo el README al pie de la letra: `py -3.12 -m venv .venv` + `pip install -r requirements-dev.txt` → instalación limpia sin errores.
- `python -m pytest` desde ese checkout limpio (sin exportar `PYTHONPATH` manualmente) → 49/49 tests pasan, confirma que `pytest.ini` resuelve el layout `src/` tal como se documenta en el README.
- Se copiaron `credentials.json`/`.env`/`token.json` reales (los secrets que el usuario ya obtuvo, consistente con los prerrequisitos del README — no se regeneran en cada clone) y se corrió `PYTHONPATH=src python -m calendar_agent.main "hoy"` y `"¿qué tengo el viernes?"` contra el calendario real desde el checkout limpio → ambos funcionaron end-to-end (OAuth refrescado en silencio, sin re-pedir login; lectura NL real vía Anthropic + Calendar).
- **No se re-verificó el consent flow de OAuth desde cero** (clic de "permitir acceso" en navegador) — no hay navegador disponible en el entorno de ejecución del agente, y H1 ya lo verificó en vivo. Documentado como limitación conocida de esta verificación, no como gap silencioso.
- Directorio temporal borrado después de la verificación (contenía copias de credenciales reales).

**Fecha:** 2026-06-25 (H6).
