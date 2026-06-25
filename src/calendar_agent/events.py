"""Query Google Calendar events by date range and render them in natural language."""

import json
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

LOCAL_TIMEZONE = "America/Lima"


class CalendarError(Exception):
    """Raised for any Calendar API failure, instead of letting raw HttpError propagate."""


def _log_event(level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}))


def _execute_with_retry(request, max_retries: int = 3, base_delay: float = 1.0):
    """Run a Google API request, retrying on 429 (rate limit) with exponential
    backoff. Any other HttpError, or a 429 that's still failing after the last
    retry, propagates to the caller's own error handling."""
    for attempt in range(max_retries):
        try:
            return request.execute()
        except HttpError as exc:
            if exc.status_code == 429 and attempt < max_retries - 1:
                _log_event(logging.WARNING, "calendar_rate_limited", attempt=attempt + 1)
                time.sleep(base_delay * (2**attempt))
                continue
            raise


def _calendar_error_message(action: str, exc: HttpError) -> str:
    status = exc.status_code
    if status == 403:
        return f"No tienes permiso para {action}."
    if status == 404:
        return f"No se pudo {action}: el evento no existe (puede haber sido borrado)."
    if status == 429:
        return f"No se pudo {action}: Google Calendar está limitando las solicitudes. Intenta de nuevo en un momento."
    return f"No se pudo {action} (error HTTP {status})."


def today_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def tomorrow_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    start, end = today_range(now)
    return start + timedelta(days=1), end + timedelta(days=1)


def custom_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    tzinfo = datetime.now().astimezone().tzinfo
    start = datetime.combine(date.fromisoformat(start_date), datetime.min.time(), tzinfo)
    end = datetime.combine(date.fromisoformat(end_date), datetime.min.time(), tzinfo) + timedelta(days=1)
    return start, end


def list_events(service, time_min: datetime, time_max: datetime) -> list[dict]:
    events = []
    page_token = None

    while True:
        try:
            response = _execute_with_retry(
                service.events().list(
                    calendarId="primary",
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
            )
        except HttpError as exc:
            _log_event(logging.ERROR, "calendar_list_failed", status=exc.status_code)
            raise CalendarError(_calendar_error_message("consultar el calendario", exc)) from exc

        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events


def _local_time(time_field: dict) -> datetime:
    """Google's API always returns dateTime in UTC ('Z'); the timeZone field is
    metadata, not a display format. Convert explicitly before showing it to the user."""
    dt = datetime.fromisoformat(time_field["dateTime"])
    tz_name = time_field.get("timeZone") or LOCAL_TIMEZONE
    return dt.astimezone(ZoneInfo(tz_name))


def _format_event_line(event: dict) -> str:
    title = event.get("summary") or "(Sin título)"
    start = event.get("start", {})
    end = event.get("end", {})

    if "dateTime" in start:
        start_time = _local_time(start).strftime("%H:%M")
        end_time = _local_time(end).strftime("%H:%M")
        return f"- {start_time} - {end_time}: {title}"

    return f"- Todo el día: {title}"


def format_events_natural_language(events: list[dict], range_label: str) -> str:
    if not events:
        return f"No tienes eventos programados {range_label}."

    lines = [_format_event_line(event) for event in events]
    header = f"Tienes {len(events)} evento(s) {range_label}:"
    return "\n".join([header, *lines])


def describe_event(event: dict) -> str:
    title = event.get("summary") or "(Sin título)"
    start = event.get("start", {})
    if "dateTime" in start:
        start_dt = _local_time(start)
        return f"{title} ({start_dt.strftime('%Y-%m-%d %H:%M')})"
    return f"{title} ({start.get('date', '')})"


def create_event(service, titulo: str, fecha: str, hora: str, duracion_minutos: int) -> dict:
    tzinfo = datetime.now().astimezone().tzinfo
    start = datetime.combine(date.fromisoformat(fecha), datetime.strptime(hora, "%H:%M").time(), tzinfo)
    end = start + timedelta(minutes=duracion_minutos)
    body = {
        "summary": titulo,
        "start": {"dateTime": start.isoformat(), "timeZone": LOCAL_TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": LOCAL_TIMEZONE},
    }

    try:
        return _execute_with_retry(service.events().insert(calendarId="primary", body=body))
    except HttpError as exc:
        _log_event(logging.ERROR, "calendar_create_failed", status=exc.status_code)
        raise CalendarError(_calendar_error_message("crear el evento", exc)) from exc


def find_event_by_description(
    service, descripcion: str, now: datetime | None = None, window_days: int = 30
) -> dict | None:
    now = now or datetime.now().astimezone()
    time_max = now + timedelta(days=window_days)

    try:
        response = _execute_with_retry(
            service.events().list(
                calendarId="primary",
                q=descripcion,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=1,
            )
        )
    except HttpError as exc:
        _log_event(logging.ERROR, "calendar_search_failed", status=exc.status_code)
        raise CalendarError(_calendar_error_message("buscar el evento", exc)) from exc

    items = response.get("items", [])
    return items[0] if items else None


def move_event(service, event_id: str, nueva_fecha: str, nueva_hora: str) -> dict:
    try:
        event = _execute_with_retry(service.events().get(calendarId="primary", eventId=event_id))
    except HttpError as exc:
        _log_event(logging.ERROR, "calendar_get_failed", status=exc.status_code)
        raise CalendarError(_calendar_error_message("leer el evento a mover", exc)) from exc

    original_start = event.get("start", {})
    original_end = event.get("end", {})

    if "dateTime" in original_start and "dateTime" in original_end:
        duration = datetime.fromisoformat(original_end["dateTime"]) - datetime.fromisoformat(
            original_start["dateTime"]
        )
    else:
        duration = timedelta(hours=1)

    tzinfo = datetime.now().astimezone().tzinfo
    new_start = datetime.combine(date.fromisoformat(nueva_fecha), datetime.strptime(nueva_hora, "%H:%M").time(), tzinfo)
    new_end = new_start + duration

    body = {
        "start": {"dateTime": new_start.isoformat(), "timeZone": LOCAL_TIMEZONE},
        "end": {"dateTime": new_end.isoformat(), "timeZone": LOCAL_TIMEZONE},
    }

    try:
        return _execute_with_retry(
            service.events().patch(calendarId="primary", eventId=event_id, body=body)
        )
    except HttpError as exc:
        _log_event(logging.ERROR, "calendar_move_failed", status=exc.status_code)
        raise CalendarError(_calendar_error_message("mover el evento", exc)) from exc


def delete_event(service, event_id: str) -> None:
    try:
        _execute_with_retry(service.events().delete(calendarId="primary", eventId=event_id))
    except HttpError as exc:
        _log_event(logging.ERROR, "calendar_delete_failed", status=exc.status_code)
        raise CalendarError(_calendar_error_message("borrar el evento", exc)) from exc
