"""Shared fixtures for the calendar_agent unit test suite."""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_match_event_llm():
    """Prevent _match_event_llm from requiring ANTHROPIC_API_KEY in unit tests.

    Unit tests exercise the HITL confirmation flow, not LLM event identification.
    Returns the first event from the candidate list, matching the single-event
    mock data each test sets up on the service object.
    """
    with patch(
        "calendar_agent.events._match_event_llm",
        side_effect=lambda events, desc: events[0] if events else None,
    ):
        yield
