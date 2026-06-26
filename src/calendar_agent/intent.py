"""Extract structured intent + parameters from natural-language calendar requests
via forced Anthropic tool-use. No free-text parsing of the LLM's reply."""

import json
import logging
import os
from datetime import date

from anthropic import Anthropic, APIError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

TOOLS = [
    {
        "name": "read_events",
        "description": "Extrae el rango de fechas que el usuario quiere consultar en su calendario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_inicio": {
                    "type": "string",
                    "description": "Fecha de inicio del rango, formato ISO YYYY-MM-DD.",
                },
                "fecha_fin": {
                    "type": "string",
                    "description": "Fecha de fin del rango (inclusive), formato ISO YYYY-MM-DD.",
                },
            },
            "required": ["fecha_inicio", "fecha_fin"],
        },
    },
    {
        "name": "create_event",
        "description": "Extrae los datos para crear un nuevo evento en el calendario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título del evento."},
                "fecha": {"type": "string", "description": "Fecha del evento, formato ISO YYYY-MM-DD."},
                "hora": {"type": "string", "description": "Hora de inicio, formato HH:MM (24h)."},
                "duracion_minutos": {"type": "integer", "description": "Duración del evento en minutos."},
            },
            "required": ["titulo", "fecha", "hora", "duracion_minutos"],
        },
    },
    {
        "name": "move_event",
        "description": "Extrae los datos para mover/reagendar un evento existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "descripcion_evento": {
                    "type": "string",
                    "description": "Descripción que identifica el evento a mover (título y/u hora original mencionada por el usuario).",
                },
                "nueva_fecha": {
                    "type": "string",
                    "description": (
                        "Nueva fecha, formato ISO YYYY-MM-DD. Omite este campo si el usuario solo "
                        "cambia la hora y no menciona una fecha nueva."
                    ),
                },
                "nueva_hora": {
                    "type": "string",
                    "description": (
                        "Nueva hora, formato HH:MM (24h). Omite este campo si el usuario solo cambia "
                        "la fecha y no menciona una hora nueva."
                    ),
                },
            },
            "required": ["descripcion_evento"],
        },
    },
    {
        "name": "delete_event",
        "description": "Extrae los datos para borrar un evento existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "descripcion_evento": {
                    "type": "string",
                    "description": "Descripción que identifica el evento a borrar (título y/u hora mencionada por el usuario).",
                },
            },
            "required": ["descripcion_evento"],
        },
    },
    {
        "name": "request_clarification",
        "description": (
            "Úsala cuando la fecha/hora es ambigua, o cuando el usuario NO da ninguna descripción "
            "identificadora del evento (ej. 'muévelo', 'bórralo' sin título, nombre ni horario). "
            "Si el usuario menciona cualquier descriptor parcial (nombre, tipo, participante, horario), "
            "extráelo como descripcion_evento — la resolución entre múltiples candidatos la maneja "
            "otra capa que tiene acceso a los eventos reales."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "Pregunta concreta para pedirle al usuario la aclaración que falta.",
                },
            },
            "required": ["pregunta"],
        },
    },
]


class IntentError(Exception):
    """Raised for any intent-extraction failure, instead of letting raw Anthropic SDK
    exceptions propagate."""


def _log_event(level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}))


def _build_system_prompt(today: date) -> str:
    return (
        f"Hoy es {today.isoformat()}. "
        "Interpreta la solicitud del usuario sobre su calendario y llama exactamente una "
        "de las herramientas disponibles con los parámetros extraídos. "
        "Cuando el usuario mencione un día de la semana sin fecha exacta (ej. 'el jueves'), "
        "interpreta la PRÓXIMA ocurrencia de ese día a partir de hoy (sin incluir hoy mismo "
        "si hoy es ese día). Todas las fechas en tu respuesta deben ir en formato ISO YYYY-MM-DD. "
        "Al mover un evento, si el usuario solo menciona una nueva fecha (sin hora) o solo una "
        "nueva hora (sin fecha), omite por completo el campo que no mencionó — NUNCA inventes "
        "un valor de relleno para ese campo. "
        "Si el usuario pide mover o borrar un evento sin dar NINGÚN descriptor identificador "
        "(ej. 'muévelo', 'bórralo' sin título, nombre, tipo ni horario), o si la fecha/hora sigue "
        "siendo ambigua después de aplicar la regla anterior, llama a 'request_clarification'. "
        "Si el usuario menciona cualquier descriptor parcial del evento (ej. 'el café', 'la reunión "
        "de las 3', 'el evento con Pedro'), extráelo en descripcion_evento — NO llames a "
        "request_clarification solo porque el descriptor sea breve o pueda tener varios matches."
    )


def extract_intent(text: str, today: date | None = None, history: list[dict] | None = None) -> dict:
    today = today or date.today()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise IntentError("Falta ANTHROPIC_API_KEY en el entorno (.env).")

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    client = Anthropic(api_key=api_key)

    messages = [*(history or []), {"role": "user", "content": text}]

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_build_system_prompt(today),
            messages=messages,
            tools=TOOLS,
            tool_choice={"type": "any"},
        )
    except APIError as exc:
        _log_event(logging.ERROR, "intent_extraction_failed", error_type=type(exc).__name__)
        raise IntentError("Falló la llamada al modelo de interpretación de lenguaje natural.") from exc

    _log_event(
        logging.INFO,
        "intent_extraction_tokens",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        _log_event(logging.ERROR, "intent_extraction_no_tool_use")
        raise IntentError("El modelo no devolvió una intención estructurada.")

    return {"intent": tool_use.name, "params": tool_use.input}
