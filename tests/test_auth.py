"""Mocked tests for OAuth credential handling. No live Google API calls."""

import json
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from calendar_agent.auth import AuthError, get_credentials, save_credentials


def _fake_creds(valid=False, expired=False, refresh_token=None):
    creds = MagicMock()
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = refresh_token
    creds.to_json.return_value = json.dumps({"token": "fake"})
    return creds


def test_returns_loaded_token_without_flow_when_valid(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")
    valid_creds = _fake_creds(valid=True)

    with patch("calendar_agent.auth.Credentials.from_authorized_user_file", return_value=valid_creds), \
         patch("calendar_agent.auth.InstalledAppFlow") as mock_flow:
        result = get_credentials(token_path=str(token_path))

    assert result is valid_creds
    mock_flow.from_client_secrets_file.assert_not_called()


def test_refreshes_expired_token_without_flow(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")
    expired_creds = _fake_creds(valid=False, expired=True, refresh_token="rt")

    with patch("calendar_agent.auth.Credentials.from_authorized_user_file", return_value=expired_creds), \
         patch("calendar_agent.auth.InstalledAppFlow") as mock_flow:
        result = get_credentials(token_path=str(token_path))

    assert result is expired_creds
    expired_creds.refresh.assert_called_once()
    mock_flow.from_client_secrets_file.assert_not_called()
    assert token_path.read_text() == json.dumps({"token": "fake"})


def test_falls_back_to_flow_when_no_token_file(tmp_path):
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "credentials.json"
    new_creds = _fake_creds(valid=True)
    mock_flow_instance = MagicMock()
    mock_flow_instance.run_local_server.return_value = new_creds

    with patch("calendar_agent.auth.Credentials.from_authorized_user_file", side_effect=FileNotFoundError), \
         patch("calendar_agent.auth.InstalledAppFlow") as mock_flow:
        mock_flow.from_client_secrets_file.return_value = mock_flow_instance
        result = get_credentials(
            credentials_path=str(credentials_path), token_path=str(token_path)
        )

    assert result is new_creds
    mock_flow.from_client_secrets_file.assert_called_once_with(
        str(credentials_path), ["https://www.googleapis.com/auth/calendar"]
    )
    assert token_path.read_text() == json.dumps({"token": "fake"})


def test_falls_back_to_flow_when_refresh_fails(tmp_path):
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "credentials.json"
    expired_creds = _fake_creds(valid=False, expired=True, refresh_token="rt")
    expired_creds.refresh.side_effect = RefreshError("revoked")
    new_creds = _fake_creds(valid=True)
    mock_flow_instance = MagicMock()
    mock_flow_instance.run_local_server.return_value = new_creds

    with patch("calendar_agent.auth.Credentials.from_authorized_user_file", return_value=expired_creds), \
         patch("calendar_agent.auth.InstalledAppFlow") as mock_flow:
        mock_flow.from_client_secrets_file.return_value = mock_flow_instance
        result = get_credentials(
            credentials_path=str(credentials_path), token_path=str(token_path)
        )

    assert result is new_creds
    mock_flow.from_client_secrets_file.assert_called_once()


def test_raises_autherror_when_credentials_json_missing(tmp_path):
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "missing_credentials.json"

    with patch("calendar_agent.auth.Credentials.from_authorized_user_file", side_effect=FileNotFoundError), \
         patch("calendar_agent.auth.InstalledAppFlow") as mock_flow:
        mock_flow.from_client_secrets_file.side_effect = FileNotFoundError

        with pytest.raises(AuthError):
            get_credentials(
                credentials_path=str(credentials_path), token_path=str(token_path)
            )


def test_save_credentials_write_failure_raises_autherror(tmp_path):
    creds = _fake_creds(valid=True)
    bad_path = tmp_path / "no_such_dir" / "token.json"

    with pytest.raises(AuthError):
        save_credentials(creds, token_path=str(bad_path))
