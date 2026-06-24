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
