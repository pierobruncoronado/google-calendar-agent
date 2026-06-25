"""Mocked tests for the H4 HITL write flow (create/move/delete) and the H5
ambiguity-clarification dispatch. No live API calls."""

from unittest.mock import MagicMock, patch

from calendar_agent.main import (
    _handle_create_event,
    _handle_delete_event,
    _handle_move_event,
    _handle_nl_text,
)


def _yes(_prompt):
    return "si"


def _no(_prompt):
    return "no"


def test_create_event_confirmed_calls_api():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}
    params = {"titulo": "Dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}

    exit_code = _handle_create_event(service, params, input_fn=_yes)

    assert exit_code == 0
    service.events.return_value.insert.assert_called_once()


def test_create_event_declined_does_not_call_api():
    service = MagicMock()
    params = {"titulo": "Dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}

    exit_code = _handle_create_event(service, params, input_fn=_no)

    assert exit_code == 0
    service.events.return_value.insert.assert_not_called()


def test_move_event_found_and_confirmed_calls_patch():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    service.events.return_value.get.return_value.execute.return_value = {
        "start": {"dateTime": "2026-06-24T14:00:00-05:00"},
        "end": {"dateTime": "2026-06-24T15:00:00-05:00"},
    }
    params = {"descripcion_evento": "reunión de las 2", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    exit_code = _handle_move_event(service, params, input_fn=_yes)

    assert exit_code == 0
    service.events.return_value.patch.assert_called_once()


def test_move_event_declined_does_not_call_patch():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    params = {"descripcion_evento": "reunión de las 2", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    exit_code = _handle_move_event(service, params, input_fn=_no)

    assert exit_code == 0
    service.events.return_value.patch.assert_not_called()


def test_move_event_not_found_does_not_prompt_or_call_patch():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    params = {"descripcion_evento": "reunión inexistente", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    def fail_if_called(_prompt):
        raise AssertionError("no debería pedir confirmación si no encontró el evento")

    exit_code = _handle_move_event(service, params, input_fn=fail_if_called)

    assert exit_code == 1
    service.events.return_value.patch.assert_not_called()


def test_delete_event_found_and_confirmed_calls_delete():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    params = {"descripcion_evento": "reunión de las 2"}

    exit_code = _handle_delete_event(service, params, input_fn=_yes)

    assert exit_code == 0
    service.events.return_value.delete.assert_called_once()


def test_delete_event_declined_does_not_call_delete():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    params = {"descripcion_evento": "reunión de las 2"}

    exit_code = _handle_delete_event(service, params, input_fn=_no)

    assert exit_code == 0
    service.events.return_value.delete.assert_not_called()


def test_delete_event_not_found_does_not_prompt_or_call_delete():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    params = {"descripcion_evento": "reunión inexistente"}

    def fail_if_called(_prompt):
        raise AssertionError("no debería pedir confirmación si no encontró el evento")

    exit_code = _handle_delete_event(service, params, input_fn=fail_if_called)

    assert exit_code == 1
    service.events.return_value.delete.assert_not_called()


def test_request_clarification_prints_question_and_does_not_touch_calendar(capsys):
    service = MagicMock()
    params = {"pregunta": "¿A qué evento te refieres?"}

    def fail_if_called(_prompt):
        raise AssertionError("no debería pedir confirmación si la intención es aclarar")

    with patch(
        "calendar_agent.main.extract_intent",
        return_value={"intent": "request_clarification", "params": params},
    ):
        exit_code = _handle_nl_text(service, "muévelo al jueves", input_fn=fail_if_called)

    assert exit_code == 0
    assert "¿A qué evento te refieres?" in capsys.readouterr().out
    service.events.assert_not_called()
