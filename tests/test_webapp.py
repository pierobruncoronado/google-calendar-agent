"""Mocked tests for the Capa-2 FastAPI web frontend. No live API calls."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from calendar_agent.auth import AuthError
from calendar_agent.webapp import app


def test_index_serves_html():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_chat_round_trips_through_handle_turn_and_sets_session_cookie():
    client = TestClient(app)
    fake_service = MagicMock()

    with (
        patch("calendar_agent.webapp._get_service", return_value=fake_service),
        patch("calendar_agent.webapp.handle_turn", return_value="hola de vuelta") as mock_handle,
    ):
        response = client.post("/chat", json={"message": "hola"})

    assert response.status_code == 200
    assert response.json() == {"reply": "hola de vuelta"}
    assert "session_id" in response.cookies
    mock_handle.assert_called_once()


def test_chat_reuses_same_session_state_across_requests():
    client = TestClient(app)
    fake_service = MagicMock()
    seen_states = []

    def fake_handle_turn(service, state, message):
        seen_states.append(state)
        return "ok"

    with (
        patch("calendar_agent.webapp._get_service", return_value=fake_service),
        patch("calendar_agent.webapp.handle_turn", side_effect=fake_handle_turn),
    ):
        client.post("/chat", json={"message": "uno"})
        client.post("/chat", json={"message": "dos"})

    assert len(seen_states) == 2
    assert seen_states[0] is seen_states[1]


def test_chat_returns_auth_error_message_without_crashing():
    client = TestClient(app)

    with patch("calendar_agent.webapp._get_service", side_effect=AuthError("falló la autenticación")):
        response = client.post("/chat", json={"message": "hola"})

    assert response.status_code == 200
    assert "Error de autenticación" in response.json()["reply"]
