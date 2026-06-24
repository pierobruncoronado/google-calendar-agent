"""H1 entrypoint (verify OAuth) + H2 entrypoint (read events by range)."""

import logging
import sys

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

logging.basicConfig(level=logging.INFO, format="%(message)s")


def _resolve_range(arg: str):
    if arg == "hoy":
        return today_range(), "hoy"
    if arg == "mañana":
        return tomorrow_range(), "mañana"
    return custom_range(arg, arg), f"el {arg}"


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

    try:
        (time_min, time_max), range_label = _resolve_range(sys.argv[1])
    except ValueError:
        print(f"Rango inválido: '{sys.argv[1]}'. Usa 'hoy', 'mañana' o una fecha YYYY-MM-DD.", file=sys.stderr)
        return 1

    try:
        events = list_events(service, time_min, time_max)
    except CalendarError as exc:
        print(f"Error al consultar el calendario: {exc}", file=sys.stderr)
        return 1

    print(format_events_natural_language(events, range_label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
