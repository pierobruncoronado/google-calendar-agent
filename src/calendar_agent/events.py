"""Query Google Calendar events by date range and render them in natural language."""

import json
import logging
from datetime import date, datetime, timedelta

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class CalendarError(Exception):
    """Raised for any Calendar API failure, instead of letting raw HttpError propagate."""


def _log_event(level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}))


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
            response = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            _log_event(logging.ERROR, "calendar_list_failed", status=exc.status_code)
            raise CalendarError(
                f"No se pudo consultar el calendario (error HTTP {exc.status_code})."
            ) from exc

        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events


def _format_event_line(event: dict) -> str:
    title = event.get("summary") or "(Sin título)"
    start = event.get("start", {})
    end = event.get("end", {})

    if "dateTime" in start:
        start_time = datetime.fromisoformat(start["dateTime"]).strftime("%H:%M")
        end_time = datetime.fromisoformat(end["dateTime"]).strftime("%H:%M")
        return f"- {start_time} - {end_time}: {title}"

    return f"- Todo el día: {title}"


def format_events_natural_language(events: list[dict], range_label: str) -> str:
    if not events:
        return f"No tienes eventos programados {range_label}."

    lines = [_format_event_line(event) for event in events]
    header = f"Tienes {len(events)} evento(s) {range_label}:"
    return "\n".join([header, *lines])
