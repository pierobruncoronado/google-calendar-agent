"""Stateful multi-turn conversation handling for the Capa-2 web frontend.

Reuses the same Calendar/intent building blocks as the CLI (main.py), but
returns text per turn instead of printing + blocking on input(): an HTTP
request can't hold a confirmation prompt open across turns, so the pending
action is parked in `state` and resumed on the next call to handle_turn().
"""

from datetime import date

from calendar_agent.events import (
    AmbiguousEventError,
    CalendarError,
    create_event,
    custom_range,
    delete_event,
    describe_event,
    describe_new_schedule,
    find_event_by_description,
    format_events_natural_language,
    list_events,
    move_event,
)
from calendar_agent.intent import IntentError, extract_intent

_CONFIRM_YES = {"si", "sí", "s", "yes", "y"}


def new_session_state() -> dict:
    return {"pending_confirmation": None, "pending_clarification": None}


def handle_turn(service, state: dict, message: str) -> str:
    if state.get("pending_confirmation"):
        return _resume_confirmation(service, state, message)
    if state.get("pending_clarification"):
        pending = state["pending_clarification"]
        state["pending_clarification"] = None
        history = [
            {"role": "user", "content": pending["original_message"]},
            {"role": "assistant", "content": pending["pregunta"]},
        ]
        return _process_message(service, state, message, history=history)
    return _process_message(service, state, message)


def _process_message(service, state: dict, text: str, history: list[dict] | None = None) -> str:
    try:
        result = extract_intent(text, today=date.today(), history=history)
    except IntentError as exc:
        return f"Error al interpretar la solicitud: {exc}"

    intent, params = result["intent"], result["params"]

    if intent == "read_events":
        time_min, time_max = custom_range(params["fecha_inicio"], params["fecha_fin"])
        try:
            events = list_events(service, time_min, time_max)
        except CalendarError as exc:
            return f"Error al consultar el calendario: {exc}"
        return format_events_natural_language(events, f"entre {params['fecha_inicio']} y {params['fecha_fin']}")

    if intent == "request_clarification":
        state["pending_clarification"] = {"original_message": text, "pregunta": params["pregunta"]}
        return params["pregunta"]

    if intent == "create_event":
        state["pending_confirmation"] = {"intent": intent, "params": params, "event": None}
        return (
            f"Voy a crear el evento '{params['titulo']}' el {params['fecha']} a las "
            f"{params['hora']} (duración {params['duracion_minutos']} min). ¿Confirmas? (sí/no)"
        )

    if intent in ("move_event", "delete_event"):
        try:
            event = find_event_by_description(service, params["descripcion_evento"])
        except AmbiguousEventError as exc:
            candidate_list = "\n".join(f"- {describe_event(c)}" for c in exc.candidates)
            pregunta = (
                f"Encontré varios eventos que podrían coincidir con "
                f"'{params['descripcion_evento']}':\n{candidate_list}\n¿A cuál te refieres?"
            )
            state["pending_clarification"] = {"original_message": text, "pregunta": pregunta}
            return pregunta
        except CalendarError as exc:
            return f"Error al buscar el evento: {exc}"
        if event is None:
            return f"No encontré ningún evento que coincida con '{params['descripcion_evento']}'."

        state["pending_confirmation"] = {"intent": intent, "params": params, "event": event}
        if intent == "move_event":
            nueva_fecha, nueva_hora = params.get("nueva_fecha"), params.get("nueva_hora")
            return (
                f"Voy a mover '{describe_event(event)}' a "
                f"{describe_new_schedule(nueva_fecha, nueva_hora)}. ¿Confirmas? (sí/no)"
            )
        return f"Voy a borrar '{describe_event(event)}'. ¿Confirmas? (sí/no)"

    return f"Intención no reconocida: {intent}"


def _resume_confirmation(service, state: dict, message: str) -> str:
    pending = state["pending_confirmation"]
    state["pending_confirmation"] = None

    if message.strip().lower() not in _CONFIRM_YES:
        return "Acción cancelada. No se modificó el calendario."

    intent, params, event = pending["intent"], pending["params"], pending["event"]

    try:
        if intent == "create_event":
            create_event(service, params["titulo"], params["fecha"], params["hora"], params["duracion_minutos"])
            return "Evento creado."
        if intent == "move_event":
            move_event(service, event["id"], params.get("nueva_fecha"), params.get("nueva_hora"))
            return "Evento movido."
        delete_event(service, event["id"])
        return "Evento borrado."
    except CalendarError as exc:
        return f"Error: {exc}"
