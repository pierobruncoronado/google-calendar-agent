# Spec — Agente conversacional de Google Calendar (v1)
*Nivel 3 (proyecto entero). Proyecto de integración para cruzar el "muro de integración" — el gap #1 de los roles Applied AI / FDE (95% de fallos enterprise son de integración, no de modelo). Estrena el sistema Max-Meta de punta a punta.*
*Estado: BORRADOR para revisión. Congelar tras tu OK.*

---

## 1. Outcome + Why
**Qué:** un agente conversacional que entiende lenguaje natural y opera sobre Google Calendar del usuario vía la API oficial, autenticado con OAuth 2.0 real. El usuario le habla ("¿qué tengo mañana?", "agéndame dentista el jueves 3pm", "mueve mi reunión de las 2 a las 4"); el agente consulta o actúa.

**Por qué (la razón de portfolio/empleo):** los 3 proyectos actuales son agentes autocontenidos sin integración con sistemas externos reales. El perfil Applied AI / FDE se define por cruzar el muro de integración: OAuth real, refresh tokens, rate limits y edge cases que la documentación del vendor no cubre. Este proyecto produce la historia que falta: "deployé un agente que actúa contra un sistema externo real con autenticación de producción y human-in-the-loop", no un demo.

## 2. Alcance y Fuera-de-alcance
**Dentro (v1):**
- Integración con Google Calendar API vía OAuth 2.0 (consent flow, access + refresh tokens).
- Operaciones de LECTURA: consultar eventos (hoy, mañana, rango, búsqueda por texto).
- Operaciones de ESCRITURA: crear, mover/reagendar, y borrar eventos.
- Interfaz conversacional en lenguaje natural (el LLM interpreta intención y extrae parámetros: fecha, hora, título, duración).
- Human-in-the-loop en acciones destructivas (ver §5).
- Manejo robusto de errores de la API (token expirado, rate limit, permisos, conflictos).

**FUERA de alcance (v1) — vinculante:**
- **Gmail** → v2 explícito. No se toca en v1.
- Multi-usuario / multi-cuenta. v1 es un solo usuario (tú).
- Frontend elaborado → la UI es secundaria; v1 puede ser CLI o interfaz mínima. (El frontend mostrable se añade como capa 2, después del núcleo de integración, NO antes.)
- Recurrencia compleja de eventos (reglas RRULE avanzadas) → si aparece, va a v2.
- Notificaciones push / sincronización en tiempo real.

## 3. Restricciones / NFRs (se deciden AQUÍ — shift-left)
- **Stack:** Python 3.12 (no 3.14 — falta wheel de psycopg2 si se usa DB). FastAPI si se expone como servicio; CLI para v1 mínimo. Anthropic SDK para el LLM. `google-api-python-client` + `google-auth-oauthlib` para Calendar.
- **Modelo:** Haiku por defecto (interpretación de intención es tarea simple). Subir solo si las evals muestran que falla la extracción de parámetros.
- **Seguridad:** OAuth tokens y client secrets SOLO en `.env` / store seguro, NUNCA en código ni en logs. Verificar `.gitignore` cubre `.env`, `token.json`, `credentials.json` ANTES del primer commit. (Patrón de exposición de credenciales documentado — esto es crítico aquí.)
- **Output estructurado:** la extracción de parámetros (fecha/hora/título) vía forced tool-use del LLM, no parseo de texto libre.
- **Costo:** medir tokens/operación, igual que el proyecto clínica.
- **Mantenimiento:** refresh token automático (no re-autenticar en cada sesión).
- **Dependencia externa (lead-time) — H3:** `ANTHROPIC_API_KEY` válida en `.env`, igual de bloqueante que `credentials.json` de Google para H1. Sin esta key, H3 no puede arrancar (la interpretación NL depende de la API de Anthropic). Obtenerla con anticipación, no al momento de implementar H3.

## 4. Decisiones previas (NO re-litigar)
- v1 = solo Calendar. Gmail es v2. (Decidido en entrevista de spec.)
- Es un AGENTE (LLM decide y actúa), no automatización pura / cron. (El valor es Applied AI, no scripting.)
- Human-in-the-loop SOLO en acciones destructivas, no en lectura. (Ver §5.)
- Un solo usuario en v1.
- Núcleo de integración primero; frontend mostrable después como capa 2.

## 5. Criterios de aceptación (EARS donde la ambigüedad cuesta caro)

**Autenticación:**
- CUANDO el usuario corre el agente por primera vez, EL SISTEMA DEBE iniciar el OAuth consent flow y guardar el refresh token de forma segura.
- CUANDO el access token está expirado, EL SISTEMA DEBE refrescarlo automáticamente usando el refresh token Y NO pedir re-autenticación al usuario.

**Lectura (sin confirmación):**
- CUANDO el usuario pregunta por sus eventos (hoy/mañana/rango), EL SISTEMA DEBE consultar la API y devolver los eventos en lenguaje natural.
- CUANDO no hay eventos en el rango consultado, EL SISTEMA DEBE decirlo explícitamente Y NO inventar eventos.

**Escritura destructiva (CON human-in-the-loop):**
- CUANDO el usuario pide crear, mover o borrar un evento, EL SISTEMA DEBE primero proponer la acción exacta (qué, cuándo, con qué detalles) Y esperar confirmación explícita del usuario ANTES de ejecutar contra la API.
- CUANDO el usuario NO confirma (o dice que no), EL SISTEMA DEBE cancelar la acción Y NO modificar el calendario.

**Identificación de eventos por descripción natural:**
- CUANDO el usuario refiere un evento en lenguaje natural ("café de mañana"), EL SISTEMA NO DEBE hacer match literal de strings contra los títulos de eventos.
- EL SISTEMA DEBE obtener la lista de eventos en la ventana temporal relevante Y usar el LLM para identificar cuál evento corresponde a la descripción del usuario (mismo patrón de forced tool-use que H3).

**Manejo de errores (el muro de integración):**
- CUANDO la API devuelve rate limit (429), EL SISTEMA DEBE reintentar con backoff Y NO crashear.
- CUANDO la API devuelve error de permisos o el evento no existe, EL SISTEMA DEBE reportar el error en lenguaje claro Y NO fallar en silencio.
- CUANDO el usuario da una fecha/hora ambigua ("el jueves" sin saber cuál), EL SISTEMA DEBE pedir aclaración Y NO asumir una interpretación.

## 6. Desglose en tareas atómicas (hitos)
- [x] **H1 — OAuth:** consent flow + guardar/refrescar tokens. Verify: autenticar una vez, segunda corrida no re-pide login.
- [x] **H2 — Lectura:** consultar eventos por rango. Verify: "¿qué tengo mañana?" devuelve eventos reales del calendario.
- [x] **H3 — Interpretación NL:** LLM extrae intención + parámetros vía tool-use. Verify: evals de extracción (fecha/hora/título correctos).
- [x] **H4 — Escritura + HITL:** crear/mover/borrar con confirmación. Verify: propone, espera OK, ejecuta solo tras confirmación.
- [x] **H5 — Errores:** backoff en 429, mensajes claros en permisos/no-existe/ambigüedad. Verify: evals de cada caso de error.
- [x] **H6 — Deploy + README reproducible.** Verify: corre desde cero siguiendo el README.
- [x] **(Capa 2, después del núcleo) — Frontend mínimo mostrable.** Web UI simple (FastAPI + HTML/JS vanilla, sin build step) con conversación multi-turno. Decisión de alcance (2026-06-25, ver DECISIONS.md): el frontend NO es CLI elaborado ni framework JS — una sola página, sin Jinja2, sin React.

**Criterios de aceptación de Capa 2 (extienden los de §5, mismo HITL, ahora multi-turno):**
- CUANDO el usuario interactúa vía la web UI, EL SISTEMA DEBE preservar el mismo comportamiento HITL de §5 (proponer la acción exacta y esperar confirmación explícita) — la confirmación ahora ocurre en un segundo turno HTTP, no bloqueando un solo request.
- CUANDO el agente pide aclaración (criterio de ambigüedad de §5) Y el usuario responde en el turno siguiente, EL SISTEMA DEBE incorporar esa respuesta junto con el mensaje original al re-extraer la intención (memoria de turno anterior), Y NO perder el contexto ni pedir que el usuario repita todo desde cero.
- CUANDO se reinicia el proceso del servidor, ES ACEPTABLE perder el estado de conversación en memoria (sin DB en v1) — no es un criterio de falla.
- El CLI existente (`main.py`) NO se modifica ni se refactoriza para esto — es una capa nueva y separada que reutiliza los mismos módulos `events.py`/`intent.py`.

## 7. Flujos = evals (el puente spec→eval)
Cada criterio EARS de §5 se copia como caso de eval. Baseline primero, luego umbral.
- Eval lectura: "¿qué tengo el viernes?" → eventos correctos del rango.
- Eval "no hay eventos": rango vacío → dice "no tienes eventos", no inventa.
- Eval extracción: "agéndame dentista jueves 3pm 1 hora" → {título: dentista, fecha: jueves, hora: 15:00, duración: 60}.
- Eval HITL: "borra mi reunión de las 2" → propone y espera, NO borra sin confirmar.
- Eval ambigüedad: "muévelo al jueves" sin contexto claro → pide aclaración.
- Eval rate limit: simular 429 → reintenta con backoff, no crashea.
- Eval costo: tokens por operación medidos.

## 8. Bucle de vida
Cuando algo cambie (bug/feature), se edita ESTE spec primero, luego el código. Decisiones nuevas → `docs/DECISIONS.md`.

## Checklist de estrés (antes de congelar)
- [x] ¿El alcance se shippea? Sí — Calendar solo, v1 acotado.
- [x] ¿Cada cosa es imprescindible para v1? Sí — lectura + escritura + HITL + errores = el muro de integración.
- [x] ¿Sé medir "funciona"? Sí — evals de §7.
- [x] ¿Lead-time externo? Sí — (1) crear proyecto en Google Cloud Console + habilitar Calendar API + OAuth consent screen (H1/H2). ARRANCAR ESTO YA (puede tardar en aprobarse el consent screen). (2) `ANTHROPIC_API_KEY` válida en `.env` (H3) — ver §3.
- [x] ¿Decisiones registradas? Sí — §4 + DECISIONS.md.
- [x] ¿Nivel de triage correcto? Sí — Nivel 3, proyecto entero, lo amerita.
