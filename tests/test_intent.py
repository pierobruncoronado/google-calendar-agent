"""Mocked tests for NL intent extraction via forced Anthropic tool-use.
No live LLM calls."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIError

from calendar_agent.intent import IntentError, extract_intent


def _fake_response(tool_name, tool_input, input_tokens=10, output_tokens=5):
    block = MagicMock(type="tool_use", name=tool_name, input=tool_input)
    block.name = tool_name
    response = MagicMock()
    response.content = [block]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def _patched_client(response=None, side_effect=None):
    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.messages.create.side_effect = side_effect
    else:
        mock_client.messages.create.return_value = response
    return patch("calendar_agent.intent.Anthropic", return_value=mock_client), mock_client


def test_extracts_read_events_intent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    response = _fake_response("read_events", {"fecha_inicio": "2026-06-26", "fecha_fin": "2026-06-26"})
    patcher, mock_client = _patched_client(response=response)

    with patcher:
        result = extract_intent("¿qué tengo el viernes?", today=date(2026, 6, 24))

    assert result == {
        "intent": "read_events",
        "params": {"fecha_inicio": "2026-06-26", "fecha_fin": "2026-06-26"},
    }
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "any"}
    assert "2026-06-24" in kwargs["system"]


def test_extracts_create_event_intent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    params = {"titulo": "dentista", "fecha": "2026-06-25", "hora": "15:00", "duracion_minutos": 60}
    response = _fake_response("create_event", params)
    patcher, _ = _patched_client(response=response)

    with patcher:
        result = extract_intent("agéndame dentista jueves 3pm 1 hora", today=date(2026, 6, 24))

    assert result == {"intent": "create_event", "params": params}


def test_extracts_move_event_intent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    params = {"descripcion_evento": "reunión de las 2", "nueva_fecha": "2026-06-24", "nueva_hora": "16:00"}
    response = _fake_response("move_event", params)
    patcher, _ = _patched_client(response=response)

    with patcher:
        result = extract_intent("mueve mi reunión de las 2 a las 4", today=date(2026, 6, 24))

    assert result == {"intent": "move_event", "params": params}


def test_extracts_delete_event_intent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    params = {"descripcion_evento": "reunión de las 2"}
    response = _fake_response("delete_event", params)
    patcher, _ = _patched_client(response=response)

    with patcher:
        result = extract_intent("borra mi reunión de las 2", today=date(2026, 6, 24))

    assert result == {"intent": "delete_event", "params": params}


def test_extracts_request_clarification_intent_for_ambiguous_event_reference(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    params = {"pregunta": "¿A qué evento te refieres? No mencionaste cuál quieres mover."}
    response = _fake_response("request_clarification", params)
    patcher, _ = _patched_client(response=response)

    with patcher:
        result = extract_intent("muévelo al jueves", today=date(2026, 6, 24))

    assert result == {"intent": "request_clarification", "params": params}


def test_logs_token_usage(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    response = _fake_response("read_events", {"fecha_inicio": "2026-06-24", "fecha_fin": "2026-06-24"}, 42, 7)
    patcher, _ = _patched_client(response=response)

    with patcher, caplog.at_level("INFO"):
        extract_intent("¿qué tengo hoy?", today=date(2026, 6, 24))

    assert any("intent_extraction_tokens" in record.message for record in caplog.records)
    assert any("42" in record.message for record in caplog.records)


def test_raises_intenterror_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(IntentError):
        extract_intent("¿qué tengo hoy?", today=date(2026, 6, 24))


def test_raises_intenterror_on_api_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    fake_request = MagicMock()
    patcher, _ = _patched_client(
        side_effect=APIError("boom", request=fake_request, body=None)
    )

    with patcher:
        with pytest.raises(IntentError):
            extract_intent("¿qué tengo hoy?", today=date(2026, 6, 24))


def test_raises_intenterror_when_no_tool_use_block(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    response = MagicMock()
    response.content = [MagicMock(type="text")]
    response.usage.input_tokens = 1
    response.usage.output_tokens = 1
    patcher, _ = _patched_client(response=response)

    with patcher:
        with pytest.raises(IntentError):
            extract_intent("hola", today=date(2026, 6, 24))
