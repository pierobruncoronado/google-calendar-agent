"""Mocked tests for Calendar event listing/formatting. No live Google API calls."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from calendar_agent.events import (
    CalendarError,
    custom_range,
    format_events_natural_language,
    list_events,
    today_range,
    tomorrow_range,
)

UTC = timezone.utc


def test_format_empty_events_says_no_events_explicitly():
    message = format_events_natural_language([], "hoy")

    assert message == "No tienes eventos programados hoy."


def test_format_single_timed_event_includes_title_and_times():
    events = [
        {
            "summary": "Dentista",
            "start": {"dateTime": "2026-06-25T15:00:00-05:00"},
            "end": {"dateTime": "2026-06-25T16:00:00-05:00"},
        }
    ]

    message = format_events_natural_language(events, "hoy")

    assert message == "Tienes 1 evento(s) hoy:\n- 15:00 - 16:00: Dentista"


def test_format_all_day_event():
    events = [
        {
            "summary": "Vacaciones",
            "start": {"date": "2026-06-25"},
            "end": {"date": "2026-06-26"},
        }
    ]

    message = format_events_natural_language(events, "hoy")

    assert message == "Tienes 1 evento(s) hoy:\n- Todo el día: Vacaciones"


def test_format_event_without_title_uses_placeholder():
    events = [
        {
            "start": {"dateTime": "2026-06-25T15:00:00-05:00"},
            "end": {"dateTime": "2026-06-25T16:00:00-05:00"},
        }
    ]

    message = format_events_natural_language(events, "hoy")

    assert "(Sin título)" in message


def test_list_events_calls_api_with_correct_range():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    result = list_events(service, time_min, time_max)

    assert result == []
    service.events.return_value.list.assert_called_once_with(
        calendarId="primary",
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        pageToken=None,
    )


def test_list_events_paginates_through_all_pages():
    service = MagicMock()
    first_page = {"items": [{"summary": "A"}], "nextPageToken": "tok2"}
    second_page = {"items": [{"summary": "B"}]}
    service.events.return_value.list.return_value.execute.side_effect = [
        first_page,
        second_page,
    ]
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    result = list_events(service, time_min, time_max)

    assert result == [{"summary": "A"}, {"summary": "B"}]
    assert service.events.return_value.list.call_count == 2
    second_call_kwargs = service.events.return_value.list.call_args_list[1].kwargs
    assert second_call_kwargs["pageToken"] == "tok2"


def test_list_events_wraps_http_error_as_calendarerror():
    service = MagicMock()
    fake_response = MagicMock(status=403, reason="Forbidden")
    service.events.return_value.list.return_value.execute.side_effect = HttpError(
        fake_response, b'{"error": {"message": "Forbidden"}}'
    )
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    with pytest.raises(CalendarError):
        list_events(service, time_min, time_max)


def test_today_range_and_tomorrow_range_use_local_day_boundaries():
    now = datetime(2026, 6, 24, 14, 30, tzinfo=UTC)

    today_start, today_end = today_range(now)
    tomorrow_start, tomorrow_end = tomorrow_range(now)

    assert today_start == datetime(2026, 6, 24, 0, 0, tzinfo=UTC)
    assert today_end == datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    assert tomorrow_start == datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    assert tomorrow_end == datetime(2026, 6, 26, 0, 0, tzinfo=UTC)
    assert today_end - today_start == timedelta(days=1)
    assert tomorrow_end - tomorrow_start == timedelta(days=1)


def test_custom_range_is_inclusive_of_end_date():
    start, end = custom_range("2026-06-25", "2026-06-27")

    assert start.date().isoformat() == "2026-06-25"
    assert end.date().isoformat() == "2026-06-28"
    assert start.hour == 0 and start.minute == 0 and start.second == 0
    assert end - start == timedelta(days=3)
