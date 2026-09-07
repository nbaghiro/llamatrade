"""Tests for Connect streaming endpoints.

The subscriber yields proto ``trading_pb2.OrderUpdate`` /
``trading_pb2.PositionUpdate`` messages directly, so the servicer just stamps the
``stream_cursor`` and re-yields them (no per-event conversion). Client
cancellation is delivered by the transport as ``asyncio.CancelledError`` into the
generator; the servicer's ``finally`` closes the subscriber regardless of how the
stream ends.
"""

from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from connectrpc.request import RequestContext

from llamatrade_proto.generated import trading_pb2

from src.grpc.servicer import TradingServicer


def _ctx() -> RequestContext:
    return cast(RequestContext, MagicMock(spec=RequestContext))


@pytest.fixture(autouse=True)
def _owned_session(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Treat the requested session as owned; TestStreamOwnership exercises the real check."""
    if request.node.get_closest_marker("real_ownership_check"):
        yield
        return
    with patch.object(TradingServicer, "_assert_session_owned", AsyncMock(return_value=None)):
        yield


class TestStreamOrderUpdates:
    """Tests for stream_order_updates endpoint."""

    async def test_stream_order_updates_yields_updates(self) -> None:
        """Test that order updates are streamed correctly with stream_cursor stamped."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())
        order_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_tail_orders(
            sid: str, *, last_seen_id: str = ""
        ) -> AsyncIterator[tuple[str, trading_pb2.OrderUpdate]]:
            yield (
                "1-0",
                trading_pb2.OrderUpdate(
                    order=trading_pb2.Order(
                        id=order_id,
                        session_id=session_id,
                        symbol="AAPL",
                        status=trading_pb2.ORDER_STATUS_FILLED,
                    ),
                    event_type="filled",
                ),
            )
            return

        mock_subscriber.tail_orders = mock_tail_orders
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.context.user_id = str(uuid4())
        mock_request.session_id = session_id
        mock_request.last_seen_id = ""

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.stream_order_updates(mock_request, _ctx()):
                responses.append(response)

            assert len(responses) == 1
            update = responses[0]
            assert update.order.id == order_id
            assert update.order.symbol == "AAPL"
            assert update.event_type == "filled"
            assert update.stream_cursor == "1-0"

    async def test_stream_order_updates_closes_subscriber(self) -> None:
        """Test that the subscriber is closed once the tail is exhausted."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_tail_orders(
            sid: str, *, last_seen_id: str = ""
        ) -> AsyncIterator[tuple[str, trading_pb2.OrderUpdate]]:
            yield (
                "1-0",
                trading_pb2.OrderUpdate(
                    order=trading_pb2.Order(id="order-123", session_id=session_id, symbol="AAPL"),
                    event_type="submitted",
                ),
            )

        mock_subscriber.tail_orders = mock_tail_orders
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.context.user_id = str(uuid4())
        mock_request.session_id = session_id
        mock_request.last_seen_id = ""

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.stream_order_updates(mock_request, _ctx()):
                responses.append(response)

            assert len(responses) == 1
            mock_subscriber.close.assert_called_once()

    async def test_stream_order_updates_handles_exception(self) -> None:
        """Test that exceptions are logged and subscriber is closed."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_tail_orders_error(
            sid: str, *, last_seen_id: str = ""
        ) -> AsyncIterator[tuple[str, trading_pb2.OrderUpdate]]:
            raise RuntimeError("Redis connection failed")
            yield  # Make it a generator

        mock_subscriber.tail_orders = mock_tail_orders_error
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.context.user_id = str(uuid4())
        mock_request.session_id = session_id
        mock_request.last_seen_id = ""

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            with pytest.raises(RuntimeError, match="Redis connection failed"):
                async for _ in servicer.stream_order_updates(mock_request, _ctx()):
                    pass

            mock_subscriber.close.assert_called_once()


class TestStreamPositionUpdates:
    """Tests for stream_position_updates endpoint."""

    async def test_stream_position_updates_yields_updates(self) -> None:
        """Test that position updates are streamed correctly with stream_cursor stamped."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_tail_positions(
            sid: str, *, last_seen_id: str = ""
        ) -> AsyncIterator[tuple[str, trading_pb2.PositionUpdate]]:
            yield (
                "1-0",
                trading_pb2.PositionUpdate(
                    position=trading_pb2.Position(
                        session_id=session_id,
                        symbol="AAPL",
                        side=trading_pb2.POSITION_SIDE_LONG,
                    ),
                    event_type="opened",
                ),
            )
            return

        mock_subscriber.tail_positions = mock_tail_positions
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.context.user_id = str(uuid4())
        mock_request.session_id = session_id
        mock_request.last_seen_id = ""

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.stream_position_updates(mock_request, _ctx()):
                responses.append(response)

            assert len(responses) == 1
            update = responses[0]
            assert update.position.symbol == "AAPL"
            assert update.event_type == "opened"
            assert update.stream_cursor == "1-0"

    async def test_stream_position_updates_closes_subscriber(self) -> None:
        """Test that the subscriber is closed once the tail is exhausted."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_tail_positions(
            sid: str, *, last_seen_id: str = ""
        ) -> AsyncIterator[tuple[str, trading_pb2.PositionUpdate]]:
            yield (
                "1-0",
                trading_pb2.PositionUpdate(
                    position=trading_pb2.Position(
                        session_id=session_id,
                        symbol="AAPL",
                        side=trading_pb2.POSITION_SIDE_LONG,
                    ),
                    event_type="opened",
                ),
            )

        mock_subscriber.tail_positions = mock_tail_positions
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.context.user_id = str(uuid4())
        mock_request.session_id = session_id
        mock_request.last_seen_id = ""

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.stream_position_updates(mock_request, _ctx()):
                responses.append(response)

            assert len(responses) == 1
            mock_subscriber.close.assert_called_once()


@pytest.mark.real_ownership_check
class TestStreamOwnership:
    """The streams are keyed by session_id only, so the servicer must verify the
    caller owns the session before tailing; otherwise any authenticated principal
    could read another tenant's live order and position flow."""

    async def _run(self, method: str, session_id: str) -> list[object]:
        request = MagicMock()
        request.context.tenant_id = str(uuid4())
        request.context.user_id = str(uuid4())
        request.session_id = session_id
        request.last_seen_id = ""
        servicer = TradingServicer()
        stream = getattr(servicer, method)(request, _ctx())
        return [item async for item in stream]

    @pytest.mark.parametrize("method", ["stream_order_updates", "stream_position_updates"])
    async def test_unowned_session_is_not_found_and_never_tails(self, method: str) -> None:
        """A session that is not the caller's yields NOT_FOUND before any tail."""
        from connectrpc.code import Code
        from connectrpc.errors import ConnectError

        subscriber = MagicMock()
        subscriber.tail_orders = MagicMock(side_effect=AssertionError("must not tail"))
        subscriber.tail_positions = MagicMock(side_effect=AssertionError("must not tail"))

        service = MagicMock()
        service.get_session = AsyncMock(return_value=None)  # not this tenant's session

        with (
            patch("src.grpc.servicer.get_trading_event_subscriber", return_value=subscriber),
            patch(
                "src.services.live_session_service.create_live_session_service",
                AsyncMock(return_value=service),
            ),
            pytest.raises(ConnectError) as excinfo,
        ):
            await self._run(method, str(uuid4()))

        assert excinfo.value.code == Code.NOT_FOUND

    @pytest.mark.parametrize("method", ["stream_order_updates", "stream_position_updates"])
    async def test_ownership_is_checked_against_the_token_tenant(self, method: str) -> None:
        """The lookup uses the tenant resolved from the token, not the wire value."""
        service = MagicMock()
        service.get_session = AsyncMock(return_value=MagicMock())
        subscriber = MagicMock()

        async def _empty(*_a: object, **_k: object):
            return
            yield  # pragma: no cover - typing only

        subscriber.tail_orders = _empty
        subscriber.tail_positions = _empty
        subscriber.close = AsyncMock()
        resolved_tenant = uuid4()

        with (
            patch("src.grpc.servicer.get_trading_event_subscriber", return_value=subscriber),
            patch(
                "src.services.live_session_service.create_live_session_service",
                AsyncMock(return_value=service),
            ),
            patch(
                "src.grpc.servicer.resolve_identity_connect",
                return_value=(resolved_tenant, uuid4()),
            ),
        ):
            await self._run(method, str(uuid4()))

        assert service.get_session.await_args.kwargs["tenant_id"] == resolved_tenant
