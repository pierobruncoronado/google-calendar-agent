"""OAuth 2.0 consent flow and token persistence for Google Calendar access."""

import json
import logging

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class AuthError(Exception):
    """Raised for any authentication failure, instead of letting raw
    google-auth/google-auth-oauthlib/googleapiclient exceptions propagate."""


def _log_event(level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}))


def get_credentials(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> Credentials:
    creds = None

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except FileNotFoundError:
        creds = None
    except (ValueError, json.JSONDecodeError) as exc:
        _log_event(logging.WARNING, "token_load_failed", error_type=type(exc).__name__)
        creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds, token_path)
            return creds
        except RefreshError as exc:
            _log_event(logging.WARNING, "token_refresh_failed", error_type=type(exc).__name__)
            creds = None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
    except FileNotFoundError as exc:
        _log_event(logging.ERROR, "credentials_file_missing", path=credentials_path)
        raise AuthError(
            f"No se encontró el archivo de credenciales OAuth en '{credentials_path}'. "
            "Descárgalo desde Google Cloud Console (OAuth client tipo Desktop app)."
        ) from exc
    except Exception as exc:
        _log_event(logging.ERROR, "oauth_consent_flow_failed", error_type=type(exc).__name__)
        raise AuthError(
            "Falló el flujo de autenticación OAuth con Google. Revisa la conexión "
            "y que el archivo de credenciales sea válido."
        ) from exc

    save_credentials(creds, token_path)
    return creds


def save_credentials(creds: Credentials, token_path: str = "token.json") -> None:
    try:
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
    except OSError as exc:
        _log_event(logging.ERROR, "token_save_failed", path=token_path, error_type=type(exc).__name__)
        raise AuthError(f"No se pudo guardar el token en '{token_path}'.") from exc


def get_calendar_service(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
):
    creds = get_credentials(credentials_path, token_path)
    return build("calendar", "v3", credentials=creds)
