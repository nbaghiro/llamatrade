"""Tests for llamatrade_proto.server.connect module."""

from unittest.mock import AsyncMock

import pytest

from llamatrade_proto.server.connect import (
    ASGIApplication,
    CombinedConnectApp,
    create_connect_routes,
)


class TestASGIApplicationProtocol:
    """Tests for ASGIApplication protocol."""

    def test_asgi_application_is_protocol(self) -> None:
        """Test ASGIApplication is a runtime checkable protocol."""
        # Should be able to check isinstance
        assert hasattr(ASGIApplication, "__call__")

    def test_valid_asgi_app_matches_protocol(self) -> None:
        """Test valid ASGI app matches the protocol."""

        class ValidASGI:
            async def __call__(self, scope, receive, send):
                pass

        app = ValidASGI()
        assert isinstance(app, ASGIApplication)

    def test_invalid_app_does_not_match_protocol(self) -> None:
        """Test invalid app does not match the protocol."""

        class InvalidApp:
            def not_call(self):
                pass

        app = InvalidApp()
        assert not isinstance(app, ASGIApplication)


class TestCreateConnectRoutes:
    """Tests for create_connect_routes function."""

    def test_create_connect_routes_returns_app(self) -> None:
        """Test create_connect_routes returns the ASGI app."""

        class MockASGI:
            async def __call__(self, scope, receive, send):
                pass

        mock_app = MockASGI()
        result = create_connect_routes(mock_app)

        assert result is mock_app

    def test_create_connect_routes_raises_for_invalid_app(self) -> None:
        """Test create_connect_routes raises TypeError for invalid app."""
        not_an_app = "not an ASGI app"

        with pytest.raises(TypeError) as exc_info:
            create_connect_routes(not_an_app)

        assert "Expected ASGI application" in str(exc_info.value)

    def test_create_connect_routes_accepts_callable_object(self) -> None:
        """Test create_connect_routes accepts callable object."""

        class CallableApp:
            async def __call__(self, scope, receive, send):
                pass

        app = CallableApp()
        result = create_connect_routes(app)

        assert result is app


class TestCombinedConnectAppInit:
    """Tests for CombinedConnectApp initialization."""

    def test_init_with_apps(self) -> None:
        """Test CombinedConnectApp initialization with apps."""

        class MockASGI:
            async def __call__(self, scope, receive, send):
                pass

        app1 = MockASGI()
        app2 = MockASGI()

        combined = CombinedConnectApp([app1, app2])

        assert len(combined._apps) == 2

    def test_init_with_empty_apps(self) -> None:
        """Test CombinedConnectApp initialization with empty apps."""
        combined = CombinedConnectApp([])

        assert combined._apps == []

    def test_init_converts_iterable_to_list(self) -> None:
        """Test CombinedConnectApp converts iterable to list."""

        class MockASGI:
            async def __call__(self, scope, receive, send):
                pass

        def app_generator():
            yield MockASGI()
            yield MockASGI()

        combined = CombinedConnectApp(app_generator())

        assert isinstance(combined._apps, list)
        assert len(combined._apps) == 2


class TestCombinedConnectAppCall:
    """Tests for CombinedConnectApp.__call__ method."""

    @pytest.mark.asyncio
    async def test_routes_to_first_matching_app(self) -> None:
        """Test request is routed to first app that handles it."""
        send_calls = []

        async def mock_send(msg):
            send_calls.append(msg)

        class App1:
            async def __call__(self, scope, receive, send):
                # Simulate successful handling
                await send({"type": "http.response.start", "status": 200})
                await send({"type": "http.response.body", "body": b"app1"})

        class App2:
            async def __call__(self, scope, receive, send):
                # Should not be called
                await send({"type": "http.response.start", "status": 200})
                await send({"type": "http.response.body", "body": b"app2"})

        combined = CombinedConnectApp([App1(), App2()])

        scope = {"type": "http", "path": "/test"}
        receive = AsyncMock()

        await combined(scope, receive, mock_send)

        # Should have handled by app1
        assert any(call.get("body") == b"app1" for call in send_calls if isinstance(call, dict))

    @pytest.mark.asyncio
    async def test_ignores_non_http_requests(self) -> None:
        """Test non-HTTP requests are ignored."""

        class MockApp:
            def __init__(self):
                self.called = False

            async def __call__(self, scope, receive, send):
                self.called = True

        app = MockApp()
        combined = CombinedConnectApp([app])

        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)

        # App should not be called for websocket
        assert not app.called

    @pytest.mark.asyncio
    async def test_tries_next_app_on_exception(self) -> None:
        """Test tries next app when one raises exception."""

        class FailingApp:
            async def __call__(self, scope, receive, send):
                raise ValueError("Not my route")

        class SuccessApp:
            def __init__(self):
                self.called = False

            async def __call__(self, scope, receive, send):
                self.called = True
                await send({"type": "http.response.start", "status": 200})
                await send({"type": "http.response.body", "body": b"success"})

        success_app = SuccessApp()
        combined = CombinedConnectApp([FailingApp(), success_app])

        scope = {"type": "http", "path": "/test"}
        receive = AsyncMock()
        send = AsyncMock()

        await combined(scope, receive, send)

        assert success_app.called

    @pytest.mark.asyncio
    async def test_returns_404_when_no_app_handles(self) -> None:
        """Test returns 404 when no app handles the request."""

        class FailingApp:
            async def __call__(self, scope, receive, send):
                raise ValueError("Not my route")

        combined = CombinedConnectApp([FailingApp()])

        scope = {"type": "http", "path": "/unknown"}
        receive = AsyncMock()

        response_started = False
        response_body = None

        async def mock_send(msg):
            nonlocal response_started, response_body
            if msg["type"] == "http.response.start":
                response_started = True
                assert msg["status"] == 404
            elif msg["type"] == "http.response.body":
                response_body = msg["body"]

        await combined(scope, receive, mock_send)

        assert response_started
        assert response_body == b"Not Found"


class TestCombinedConnectAppSend404:
    """Tests for CombinedConnectApp._send_404 method."""

    @pytest.mark.asyncio
    async def test_send_404_sends_correct_response(self) -> None:
        """Test _send_404 sends correct 404 response."""
        combined = CombinedConnectApp([])

        scope = {"type": "http"}
        messages = []

        async def mock_send(msg):
            messages.append(msg)

        await combined._send_404(scope, mock_send)

        assert len(messages) == 2
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 404
        assert messages[1]["type"] == "http.response.body"
        assert messages[1]["body"] == b"Not Found"
