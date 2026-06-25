"""H1 entrypoint (verify OAuth) + H2 entrypoint (read events by range)
+ H3 entrypoint (NL intent extraction)."""

import logging
import sys
from datetime import date

from dotenv import load_dotenv

from calendar_agent.auth import AuthError, get_calendar_service
from calendar_agent.events import (
    CalendarError,
    custom_range,
    format_events_natural_language,
    list_events,
    today_range,
    tomorrow_range,
)
from calendar_agent.intent import IntentError, extract_intent

logging.basicConfig(level=logging.INFO, format="%(message)s")

_WRITE_INTENT_LABELS = {
    "create_event": "crear",
    "move_event": "mover",
    "delete_event": "borrar",
}


def _resolve_range(arg: str):
    if arg == "hoy":
        return today_range(), "hoy"
    if arg == "mañana":
        return tomorrow_range(), "mañana"
    return custom_range(arg, arg), f"el {arg}"


def _format_write_proposal(intent: str, params: dict) -> str:
    label = _WRITE_INTENT_LABELS[intent]
    details = ", ".join(f"{key}={value}" for key, value in params.items())
    return f"Acción detectada: {label} evento ({details}). Ejecución pendiente (H4: requiere confirmación + escritura)."


def _handle_nl_text(service, text: str) -> int:
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

    print(_format_write_proposal(intent, params))
    return 0


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
