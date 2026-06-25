"""H1 entrypoint (verify OAuth) + H2 entrypoint (read events by range)
+ H3 entrypoint (NL intent extraction) + H4 entrypoint (write + HITL)."""

import logging
import sys
from datetime import date

from dotenv import load_dotenv

from calendar_agent.auth import AuthError, get_calendar_service
from calendar_agent.events import (
    CalendarError,
    create_event,
    custom_range,
    delete_event,
    describe_event,
    find_event_by_description,
    format_events_natural_language,
    list_events,
    move_event,
    today_range,
    tomorrow_range,
)
from calendar_agent.intent import IntentError, extract_intent

logging.basicConfig(level=logging.INFO, format="%(message)s")

_CONFIRM_YES = {"si", "sí", "s", "yes", "y"}


def _resolve_range(arg: str):
    if arg == "hoy":
        return today_range(), "hoy"
    if arg == "mañana":
        return tomorrow_range(), "mañana"
    return custom_range(arg, arg), f"el {arg}"


def _confirm(prompt: str, input_fn=input) -> bool:
    print(prompt)
    answer = input_fn("Confirmas? (si/no): ").strip().lower()
    return answer in _CONFIRM_YES


def _handle_create_event(service, params: dict, input_fn=input) -> int:
    proposal = (
        f"Voy a crear el evento '{params['titulo']}' el {params['fecha']} a las "
        f"{params['hora']} (duración {params['duracion_minutos']} min)."
    )
    if not _confirm(proposal, input_fn):
        print("Acción cancelada. No se modificó el calendario.")
        return 0

    try:
        create_event(service, params["titulo"], params["fecha"], params["hora"], params["duracion_minutos"])
    except CalendarError as exc:
        print(f"Error al crear el evento: {exc}", file=sys.stderr)
        return 1

    print("Evento creado.")
    return 0


def _handle_move_event(service, params: dict, input_fn=input) -> int:
    try:
        event = find_event_by_description(service, params["descripcion_evento"])
    except CalendarError as exc:
        print(f"Error al buscar el evento: {exc}", file=sys.stderr)
        return 1

    if event is None:
        print(f"No encontré ningún evento que coincida con '{params['descripcion_evento']}'.")
        return 1

    proposal = f"Voy a mover '{describe_event(event)}' a {params['nueva_fecha']} {params['nueva_hora']}."
    if not _confirm(proposal, input_fn):
        print("Acción cancelada. No se modificó el calendario.")
        return 0

    try:
        move_event(service, event["id"], params["nueva_fecha"], params["nueva_hora"])
    except CalendarError as exc:
        print(f"Error al mover el evento: {exc}", file=sys.stderr)
        return 1

    print("Evento movido.")
    return 0


def _handle_delete_event(service, params: dict, input_fn=input) -> int:
    try:
        event = find_event_by_description(service, params["descripcion_evento"])
    except CalendarError as exc:
        print(f"Error al buscar el evento: {exc}", file=sys.stderr)
        return 1

    if event is None:
        print(f"No encontré ningún evento que coincida con '{params['descripcion_evento']}'.")
        return 1

    proposal = f"Voy a borrar '{describe_event(event)}'."
    if not _confirm(proposal, input_fn):
        print("Acción cancelada. No se modificó el calendario.")
        return 0

    try:
        delete_event(service, event["id"])
    except CalendarError as exc:
        print(f"Error al borrar el evento: {exc}", file=sys.stderr)
        return 1

    print("Evento borrado.")
    return 0


def _handle_nl_text(service, text: str, input_fn=input) -> int:
    try:
        result = extract_intent(text, today=date.today())
    except IntentError as exc:
        print(f"Error al interpretar la solicitud: {exc}", file=sys.stderr)
        return 1

    intent, params = result["intent"], result["params"]

    if intent == "read_events":
        time_min, time_max = custom_range(params["fecha_inicio"], params["fecha_fin"])
        try:
            events = list_events(service, time_min, time_max)
        except CalendarError as exc:
            print(f"Error al consultar el calendario: {exc}", file=sys.stderr)
            return 1
        print(format_events_natural_language(events, f"entre {params['fecha_inicio']} y {params['fecha_fin']}"))
        return 0

    if intent == "request_clarification":
        print(params["pregunta"])
        return 0

    if intent == "create_event":
        return _handle_create_event(service, params, input_fn)
    if intent == "move_event":
        return _handle_move_event(service, params, input_fn)
    if intent == "delete_event":
        return _handle_delete_event(service, params, input_fn)

    print(f"Intención no reconocida: {intent}", file=sys.stderr)
    return 1


def main() -> int:
    load_dotenv()
    try:
        service = get_calendar_service()
    except AuthError as exc:
        print(f"Error de autenticación: {exc}", file=sys.stderr)
        return 1

    if len(sys.argv) < 2:
        print("Autenticación exitosa")
        return 0

    arg = sys.argv[1]

    try:
        (time_min, time_max), range_label = _resolve_range(arg)
    except ValueError:
        return _handle_nl_text(service, " ".join(sys.argv[1:]))

    try:
        events = list_events(service, time_min, time_max)
    except CalendarError as exc:
        print(f"Error al consultar el calendario: {exc}", file=sys.stderr)
        return 1

    print(format_events_natural_language(events, range_label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
