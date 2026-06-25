"""Mocked tests for Calendar event listing/formatting. No live Google API calls."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from calendar_agent.events import (
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
    today_range,
    tomorrow_range,
)

UTC = timezone.utc


def _http_error(status: int) -> HttpError:
    fake_response = MagicMock(status=status, reason="error")
    return HttpError(fake_response, b'{"error": {"message": "error"}}')


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


def test_describe_event_with_time():
    event = {"summary": "Dentista", "start": {"dateTime": "2026-06-25T15:00:00-05:00"}}

    assert describe_event(event) == "Dentista (2026-06-25 15:00)"


def test_describe_event_all_day():
    event = {"summary": "Vacaciones", "start": {"date": "2026-06-25"}}

    assert describe_event(event) == "Vacaciones (2026-06-25)"


def test_describe_new_schedule_with_both_fields():
    assert describe_new_schedule("2026-06-25", "16:00") == "2026-06-25 16:00"


def test_describe_new_schedule_with_only_date():
    assert describe_new_schedule("2026-06-25", None) == "2026-06-25"


def test_describe_new_schedule_with_only_time():
    assert describe_new_schedule(None, "16:00") == "16:00"


def test_describe_new_schedule_with_neither():
    assert describe_new_schedule(None, None) == "(sin cambios)"


def test_create_event_calls_insert_with_correct_body():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {"id": "abc123"}

    result = create_event(service, "Dentista", "2026-06-25", "15:00", 60)

    assert result == {"id": "abc123"}
    kwargs = service.events.return_value.insert.call_args.kwargs
    assert kwargs["calendarId"] == "primary"
    body = kwargs["body"]
    assert body["summary"] == "Dentista"
    start_dt = datetime.fromisoformat(body["start"]["dateTime"])
    end_dt = datetime.fromisoformat(body["end"]["dateTime"])
    assert start_dt.hour == 15 and start_dt.minute == 0
    assert end_dt - start_dt == timedelta(minutes=60)


def test_create_event_wraps_http_error_as_calendarerror():
    service = MagicMock()
    fake_response = MagicMock(status=403, reason="Forbidden")
    service.events.return_value.insert.return_value.execute.side_effect = HttpError(
        fake_response, b'{"error": {"message": "Forbidden"}}'
    )

    with pytest.raises(CalendarError):
        create_event(service, "Dentista", "2026-06-25", "15:00", 60)


def test_find_event_by_description_returns_first_match():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión"}]
    }

    result = find_event_by_description(service, "reunión", now=datetime(2026, 6, 24, 9, 0, tzinfo=UTC))

    assert result == {"id": "evt1", "summary": "Reunión"}
    kwargs = service.events.return_value.list.call_args.kwargs
    assert kwargs["q"] == "reunión"
    assert kwargs["calendarId"] == "primary"


def test_find_event_by_description_returns_none_when_no_match():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}

    result = find_event_by_description(service, "reunión", now=datetime(2026, 6, 24, 9, 0, tzinfo=UTC))

    assert result is None


def test_find_event_by_description_wraps_http_error_as_calendarerror():
    service = MagicMock()
    fake_response = MagicMock(status=403, reason="Forbidden")
    service.events.return_value.list.return_value.execute.side_effect = HttpError(
        fake_response, b'{"error": {"message": "Forbidden"}}'
    )

    with pytest.raises(CalendarError):
        find_event_by_description(service, "reunión", now=datetime(2026, 6, 24, 9, 0, tzinfo=UTC))


def test_move_event_preserves_duration_and_patches_new_time():
    service = MagicMock()
    service.events.return_value.get.return_value.execute.return_value = {
        "start": {"dateTime": "2026-06-24T14:00:00-05:00"},
        "end": {"dateTime": "2026-06-24T15:00:00-05:00"},
    }
    service.events.return_value.patch.return_value.execute.return_value = {"id": "evt1"}

    result = move_event(service, "evt1", "2026-06-25", "16:00")

    assert result == {"id": "evt1"}
    kwargs = service.events.return_value.patch.call_args.kwargs
    assert kwargs["eventId"] == "evt1"
    body = kwargs["body"]
    new_start = datetime.fromisoformat(body["start"]["dateTime"])
    new_end = datetime.fromisoformat(body["end"]["dateTime"])
    assert new_start.hour == 16 and new_start.date().isoformat() == "2026-06-25"
    assert new_end - new_start == timedelta(hours=1)


def test_move_event_wraps_http_error_as_calendarerror():
    service = MagicMock()
    fake_response = MagicMock(status=404, reason="Not Found")
    service.events.return_value.get.return_value.execute.side_effect = HttpError(
        fake_response, b'{"error": {"message": "Not Found"}}'
    )

    with pytest.raises(CalendarError):
        move_event(service, "evt1", "2026-06-25", "16:00")


def test_move_event_keeps_original_time_when_nueva_hora_omitted():
    service = MagicMock()
    service.events.return_value.get.return_value.execute.return_value = {
        "start": {"dateTime": "2026-06-24T14:00:00-05:00"},
        "end": {"dateTime": "2026-06-24T15:00:00-05:00"},
    }
    service.events.return_value.patch.return_value.execute.return_value = {"id": "evt1"}

    move_event(service, "evt1", nueva_fecha="2026-06-25")

    body = service.events.return_value.patch.call_args.kwargs["body"]
    new_start = datetime.fromisoformat(body["start"]["dateTime"])
    assert new_start.date().isoformat() == "2026-06-25"
    assert new_start.hour == 14 and new_start.minute == 0


def test_move_event_keeps_original_date_when_nueva_fecha_omitted():
    service = MagicMock()
    service.events.return_value.get.return_value.execute.return_value = {
        "start": {"dateTime": "2026-06-24T14:00:00-05:00"},
        "end": {"dateTime": "2026-06-24T15:00:00-05:00"},
    }
    service.events.return_value.patch.return_value.execute.return_value = {"id": "evt1"}

    move_event(service, "evt1", nueva_hora="16:00")

    body = service.events.return_value.patch.call_args.kwargs["body"]
    new_start = datetime.fromisoformat(body["start"]["dateTime"])
    assert new_start.date().isoformat() == "2026-06-24"
    assert new_start.hour == 16


def test_delete_event_calls_delete_with_event_id():
    service = MagicMock()
    service.events.return_value.delete.return_value.execute.return_value = {}

    delete_event(service, "evt1")

    kwargs = service.events.return_value.delete.call_args.kwargs
    assert kwargs["calendarId"] == "primary"
    assert kwargs["eventId"] == "evt1"


def test_delete_event_wraps_http_error_as_calendarerror():
    service = MagicMock()
    fake_response = MagicMock(status=404, reason="Not Found")
    service.events.return_value.delete.return_value.execute.side_effect = HttpError(
        fake_response, b'{"error": {"message": "Not Found"}}'
    )

    with pytest.raises(CalendarError):
        delete_event(service, "evt1")


def test_list_events_retries_on_429_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("calendar_agent.events.time.sleep", lambda s: sleeps.append(s))
    service = MagicMock()
    service.events.return_value.list.return_value.execute.side_effect = [
        _http_error(429),
        _http_error(429),
        {"items": [{"summary": "A"}]},
    ]
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    result = list_events(service, time_min, time_max)

    assert result == [{"summary": "A"}]
    assert sleeps == [1.0, 2.0]


def test_list_events_raises_calendarerror_after_exhausting_429_retries(monkeypatch):
    monkeypatch.setattr("calendar_agent.events.time.sleep", lambda s: None)
    service = MagicMock()
    service.events.return_value.list.return_value.execute.side_effect = _http_error(429)
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    with pytest.raises(CalendarError, match="limitando"):
        list_events(service, time_min, time_max)

    assert service.events.return_value.list.return_value.execute.call_count == 3


def test_list_events_does_not_retry_on_non_429_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr("calendar_agent.events.time.sleep", lambda s: sleeps.append(s))
    service = MagicMock()
    service.events.return_value.list.return_value.execute.side_effect = _http_error(500)
    time_min = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)
    time_max = datetime(2026, 6, 26, 0, 0, tzinfo=UTC)

    with pytest.raises(CalendarError):
        list_events(service, time_min, time_max)

    assert sleeps == []
    assert service.events.return_value.list.return_value.execute.call_count == 1


def test_move_event_403_gives_clear_permission_message():
    service = MagicMock()
    service.events.return_value.get.return_value.execute.side_effect = _http_error(403)

    with pytest.raises(CalendarError, match="permiso"):
        move_event(service, "evt1", "2026-06-25", "16:00")


def test_delete_event_404_gives_clear_not_found_message():
    service = MagicMock()
    service.events.return_value.delete.return_value.execute.side_effect = _http_error(404)

    with pytest.raises(CalendarError, match="no existe"):
        delete_event(service, "evt1")
