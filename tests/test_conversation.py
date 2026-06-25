"""Mocked tests for the Capa-2 multi-turn conversation handler. No live API calls."""

from unittest.mock import MagicMock, patch

from calendar_agent.conversation import handle_turn, new_session_state


def _intent_response(intent, params):
    return {"intent": intent, "params": params}


def test_read_events_replies_directly_without_pending_state():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    state = new_session_state()
    params = {"fecha_inicio": "2026-06-26", "fecha_fin": "2026-06-26"}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("read_events", params)):
        reply = handle_turn(service, state, "¿qué tengo el viernes?")

    assert "No tienes eventos" in reply
    assert state["pending_confirmation"] is None
    assert state["pending_clarification"] is None


def test_create_event_then_confirm_executes():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}
    state = new_session_state()
    params = {"titulo": "Dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("create_event", params)):
        proposal = handle_turn(service, state, "agéndame dentista")

    assert "Confirmas" in proposal
    assert state["pending_confirmation"] is not None

    reply = handle_turn(service, state, "si")

    assert reply == "Evento creado."
    assert state["pending_confirmation"] is None
    service.events.return_value.insert.assert_called_once()


def test_create_event_then_decline_does_not_call_api():
    service = MagicMock()
    state = new_session_state()
    params = {"titulo": "Dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("create_event", params)):
        handle_turn(service, state, "agéndame dentista")

    reply = handle_turn(service, state, "no")

    assert reply == "Acción cancelada. No se modificó el calendario."
    assert state["pending_confirmation"] is None
    service.events.return_value.insert.assert_not_called()


def test_move_event_found_then_confirmed_calls_patch():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    service.events.return_value.get.return_value.execute.return_value = {
        "start": {"dateTime": "2026-06-24T14:00:00-05:00"},
        "end": {"dateTime": "2026-06-24T15:00:00-05:00"},
    }
    state = new_session_state()
    params = {"descripcion_evento": "reunión de las 2", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("move_event", params)):
        proposal = handle_turn(service, state, "mueve mi reunión de las 2")

    assert "Confirmas" in proposal

    reply = handle_turn(service, state, "si")

    assert reply == "Evento movido."
    service.events.return_value.patch.assert_called_once()


def test_move_event_not_found_does_not_set_pending_confirmation():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}
    state = new_session_state()
    params = {"descripcion_evento": "reunión inexistente", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("move_event", params)):
        reply = handle_turn(service, state, "mueve mi reunión")

    assert "No encontré" in reply
    assert state["pending_confirmation"] is None


def test_delete_event_then_confirm_calls_delete():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    state = new_session_state()
    params = {"descripcion_evento": "reunión de las 2"}

    with patch("calendar_agent.conversation.extract_intent", return_value=_intent_response("delete_event", params)):
        handle_turn(service, state, "borra mi reunión de las 2")

    reply = handle_turn(service, state, "si")

    assert reply == "Evento borrado."
    service.events.return_value.delete.assert_called_once()


def test_clarification_then_followup_resolves_with_history():
    service = MagicMock()
    state = new_session_state()
    pregunta = "¿Qué evento quieres mover?"

    with patch(
        "calendar_agent.conversation.extract_intent",
        return_value=_intent_response("request_clarification", {"pregunta": pregunta}),
    ):
        reply = handle_turn(service, state, "muévelo al jueves")

    assert reply == pregunta
    assert state["pending_clarification"] is not None
    assert state["pending_confirmation"] is None

    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt1", "summary": "Reunión", "start": {"dateTime": "2026-06-24T14:00:00-05:00"}}]
    }
    move_params = {"descripcion_evento": "reunión de las 2", "nueva_fecha": "2026-06-25", "nueva_hora": "16:00"}

    with patch(
        "calendar_agent.conversation.extract_intent",
        return_value=_intent_response("move_event", move_params),
    ) as mock_extract:
        proposal = handle_turn(service, state, "mi reunión de las 2")

    assert "Confirmas" in proposal
    assert state["pending_clarification"] is None
    kwargs = mock_extract.call_args.kwargs
    assert kwargs["history"] == [
        {"role": "user", "content": "muévelo al jueves"},
        {"role": "assistant", "content": pregunta},
    ]
