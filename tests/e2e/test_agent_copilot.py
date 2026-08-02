"""E2E: the AI copilot conversation surface (AgentService).

Mirrors the copilot UI: the sidebar lists prior sessions (``ListSessions``) and
opens one with its full history (``GetSession``); the composer seeds contextual
suggestions (``GetSuggestedPrompts``); a new chat is a ``CreateSession`` and the
trash icon a ``DeleteSession``; a proposed strategy surfaces as a pending
``PendingArtifact`` the drawer fetches via ``GetArtifact``. These read/commit
legs are deterministic and always run against the seeded demo tenant (3 sessions,
10 messages, 1 pending artifact) plus a throwaway tenant for the mutating path.

The live turn — ``StreamMessage`` against the real model (google/gemini) — is
non-deterministic and costs tokens, so it is gated behind ``E2E_LIVE_LLM=1`` and
asserts stream *shape* (deltas plus a terminal COMPLETE), never wording.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .client import MeshClient, status_is

pytestmark = pytest.mark.e2e

# StreamEventType enum members as (proto name, number) — Connect-JSON renders an
# enum as either form, so every check goes through ``status_is``.
_CONTENT_DELTA = ("STREAM_EVENT_TYPE_CONTENT_DELTA", 1)
_THINKING_DELTA = ("STREAM_EVENT_TYPE_THINKING_DELTA", 8)
_ERROR = ("STREAM_EVENT_TYPE_ERROR", 5)
_COMPLETE = ("STREAM_EVENT_TYPE_COMPLETE", 6)
_TOOL_CONFIRMATION_REQUIRED = ("STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED", 7)

# Upper bound on stream frames so a runaway turn fails loudly instead of hanging.
_MAX_STREAM_EVENTS = 400


# --- Deterministic read/commit flows (always run) ----------------------------
def test_list_sessions_returns_the_seeded_history(demo: MeshClient) -> None:
    resp = demo.call("agent", "ListSessions", {})
    sessions = resp.get("sessions", [])
    assert len(sessions) >= 3, "seeded demo should expose at least 3 copilot sessions"
    for session in sessions:
        assert session.get("id"), "every listed session must carry an id"


def test_get_session_returns_seeded_messages(demo: MeshClient) -> None:
    sessions = demo.call("agent", "ListSessions", {}).get("sessions", [])
    assert sessions, "no sessions to read"

    total_messages = 0
    saw_content = False
    for session in sessions:
        resp = demo.call(
            "agent",
            "GetSession",
            {"sessionId": session["id"], "includeMessages": True, "messageLimit": 200},
        )
        assert resp.get("session", {}).get("id") == session["id"]
        messages = resp.get("messages", [])
        total_messages += len(messages)
        for message in messages:
            assert message.get("id"), "every message must carry an id"
            assert message.get("role"), "every message must carry a role"
            if message.get("content"):
                saw_content = True
    assert total_messages >= 10, f"seeded demo should have >=10 messages, saw {total_messages}"
    assert saw_content, "seeded messages should carry text content"


def test_suggested_prompts_are_returned_for_a_page(demo: MeshClient) -> None:
    resp = demo.call("agent", "GetSuggestedPrompts", {"uiContext": {"page": "strategies"}})
    prompts = resp.get("prompts", [])
    assert prompts, "the composer should receive contextual suggested prompts"
    assert all(isinstance(p, str) and p for p in prompts)


def test_create_then_delete_session_roundtrips(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    # Runs on a throwaway tenant so listing/deleting never touches demo's history.
    client = throwaway_tenant("agent")
    assert client.call("agent", "ListSessions", {}).get("sessions", []) == []

    created = client.call(
        "agent", "CreateSession", {"initialMessage": "", "uiContext": {"page": "copilot"}}
    )
    session_id = created.get("session", {}).get("id")
    assert session_id, "CreateSession must return a session id"
    # No initial_message → no model turn, so the response carries no streamed reply.
    assert "initialResponse" not in created

    listed = client.call("agent", "ListSessions", {}).get("sessions", [])
    assert session_id in [s.get("id") for s in listed]

    deleted = client.call("agent", "DeleteSession", {"sessionId": session_id})
    assert deleted.get("success") is True

    remaining = client.call("agent", "ListSessions", {}).get("sessions", [])
    assert session_id not in [s.get("id") for s in remaining]


def test_get_artifact_returns_the_seeded_pending_strategy(demo: MeshClient) -> None:
    sessions = demo.call("agent", "ListSessions", {}).get("sessions", [])
    artifact_id = ""
    for session in sessions:
        resp = demo.call(
            "agent",
            "GetSession",
            {"sessionId": session["id"], "includeMessages": True, "messageLimit": 200},
        )
        pending = resp.get("pendingArtifacts", [])
        if pending:
            artifact_id = pending[0].get("id", "")
            break
    if not artifact_id:
        pytest.skip("no pending artifact discoverable through ListSessions/GetSession")

    resp = demo.call("agent", "GetArtifact", {"artifactId": artifact_id})
    artifact = resp.get("artifact", {})
    assert artifact.get("id") == artifact_id
    assert artifact.get("previewJson"), "a strategy artifact should carry a JSON preview"
    assert not artifact.get("isCommitted"), "the seeded artifact is still pending"


# --- Live model turn (gated: real LLM, non-deterministic + costs tokens) ------
@pytest.mark.live_llm
def test_stream_message_yields_deltas_and_a_terminal_complete(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("agent")
    session_id = (
        client.call(
            "agent", "CreateSession", {"initialMessage": "", "uiContext": {"page": "copilot"}}
        )
        .get("session", {})
        .get("id")
    )
    assert session_id

    seen: list[object] = []
    confirmation: dict[str, object] | None = None
    completed = False
    for count, event in enumerate(
        client.stream(
            "agent",
            "StreamMessage",
            {
                "sessionId": session_id,
                "content": "In one sentence, what is a moving-average crossover strategy?",
                "uiContext": {"page": "copilot"},
            },
        )
    ):
        event_type = event.get("eventType")
        seen.append(event_type)
        assert not status_is(event_type, *_ERROR), (
            f"stream surfaced an error: {event.get('errorMessage')}"
        )
        if status_is(event_type, *_TOOL_CONFIRMATION_REQUIRED):
            confirmation = event
            break
        if status_is(event_type, *_COMPLETE):
            completed = True
            break
        assert count < _MAX_STREAM_EVENTS, "stream did not terminate within the event bound"

    if confirmation is not None:
        # A proposed write action pauses the turn; declining must resume it to
        # a clean COMPLETE without executing anything.
        completed = _decline_and_drain(client, session_id, confirmation)
        assert completed, "declining the tool call did not resume the turn to COMPLETE"
    else:
        assert completed, "stream never reached a terminal COMPLETE event"
        had_delta = any(
            status_is(t, *_CONTENT_DELTA) or status_is(t, *_THINKING_DELTA) for t in seen
        )
        assert had_delta, "the model turn produced no content or thinking deltas"

    client.try_call("agent", "DeleteSession", {"sessionId": session_id})


def _decline_and_drain(
    client: MeshClient, session_id: str, confirmation: dict[str, object]
) -> bool:
    """Decline a proposed tool call and drain the resumed stream to COMPLETE."""
    completed = False
    for count, event in enumerate(
        client.stream(
            "agent",
            "ConfirmToolCall",
            {
                "sessionId": session_id,
                "confirmationId": confirmation.get("confirmationId", ""),
                "toolName": confirmation.get("toolName", ""),
                "toolArgumentsJson": confirmation.get("toolArgumentsJson", ""),
                "approved": False,
            },
        )
    ):
        event_type = event.get("eventType")
        assert not status_is(event_type, *_ERROR), (
            f"resumed stream surfaced an error: {event.get('errorMessage')}"
        )
        if status_is(event_type, *_COMPLETE):
            completed = True
            break
        assert count < _MAX_STREAM_EVENTS, "resumed stream did not terminate within the bound"
    return completed
