"""Alert service tests: every on_* maps to the right published NotificationEvent.

The service is a producer facade; assertions run against the wire records a
FakeTransport captured, so the category mapping, severity mapping, field
threading, and dedup semantics are pinned at the envelope level.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_events import EventBus, EventEnvelope
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2

from src.services.alert_service import (
    CATEGORY_BY_ALERT_TYPE,
    Alert,
    AlertPriority,
    AlertService,
    AlertType,
    get_alert_service,
)

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
SESSION_ID = UUID("22222222-2222-2222-2222-222222222222")
_E = events_pb2

pytestmark = pytest.mark.asyncio


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def service(transport: FakeTransport) -> AlertService:
    return AlertService(events=NotificationEvents(bus=EventBus(transport)))


def _published(transport: FakeTransport) -> list[EventEnvelope]:
    return [EventEnvelope.FromString(value) for _, value in transport.published]


def _payload(envelope: EventEnvelope) -> events_pb2.NotificationEvent:
    return NotificationEvents.payload(envelope)


class TestMapping:
    def test_every_alert_type_maps_to_a_category(self) -> None:
        assert set(CATEGORY_BY_ALERT_TYPE) == set(AlertType)

    async def test_send_publishes_envelope_keyed_by_tenant(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        ok = await service.send(
            Alert(
                tenant_id=TENANT_ID,
                alert_type=AlertType.ORDER_REJECTED,
                priority=AlertPriority.MEDIUM,
            )
        )
        assert ok
        assert transport.records[0].key == str(TENANT_ID)
        stream, _ = transport.published[0]
        assert stream == "notifications"
        env = _published(transport)[0]
        assert env.type == _E.EVENT_TYPE_NOTIFICATION
        assert env.tenant_id == str(TENANT_ID)

    async def test_critical_priority_maps_to_critical_severity(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.send(
            Alert(
                tenant_id=TENANT_ID,
                alert_type=AlertType.SESSION_ERROR,
                priority=AlertPriority.CRITICAL,
            )
        )
        assert _payload(_published(transport)[0]).severity == _E.NOTIFICATION_SEVERITY_CRITICAL

    async def test_non_critical_leaves_severity_to_category_default(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.send(
            Alert(
                tenant_id=TENANT_ID,
                alert_type=AlertType.ORDER_FILLED,
                priority=AlertPriority.LOW,
            )
        )
        assert _payload(_published(transport)[0]).severity == _E.NOTIFICATION_SEVERITY_UNSPECIFIED

    async def test_publish_failure_returns_false_and_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events = NotificationEvents(bus=EventBus(FakeTransport()))

        async def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("broker down")

        monkeypatch.setattr(events.bus, "publish_envelope", boom)
        service = AlertService(events=events)
        ok = await service.send(
            Alert(
                tenant_id=TENANT_ID,
                alert_type=AlertType.ORDER_FILLED,
                priority=AlertPriority.LOW,
            )
        )
        assert ok is False


class TestEventMethods:
    async def test_on_order_filled(self, service: AlertService, transport: FakeTransport) -> None:
        order = MagicMock()
        order.id = uuid4()
        order.symbol = "AAPL"
        order.side = 1  # ORDER_SIDE_BUY
        order.filled_qty = 10.0
        order.filled_avg_price = 150.25
        order.client_order_id = "lt-abc"
        await service.on_order_filled(TENANT_ID, SESSION_ID, order)

        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_ORDER_FILLED
        assert event.symbol == "AAPL"
        assert event.amount == "150.25"
        assert event.session_id == str(SESSION_ID)
        assert event.extra["client_order_id"] == "lt-abc"

    async def test_on_order_rejected(self, service: AlertService, transport: FakeTransport) -> None:
        await service.on_order_rejected(
            TENANT_ID, SESSION_ID, "TLT", "buy", 5.0, "insufficient buying power"
        )
        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_ORDER_REJECTED
        assert event.reason == "insufficient buying power"
        assert event.extra["side"] == "buy"

    async def test_on_position_events(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_position_opened(TENANT_ID, SESSION_ID, "SPY", "buy", 10.0, 500.0)
        await service.on_position_closed(TENANT_ID, SESSION_ID, "SPY", 10.0, 42.5)
        events = [_payload(e) for e in _published(transport)]
        assert events[0].category == _E.NOTIFICATION_CATEGORY_POSITION_OPENED
        assert events[1].category == _E.NOTIFICATION_CATEGORY_POSITION_CLOSED
        assert events[1].amount == "42.50"

    async def test_on_position_drift_side_mismatch_is_critical(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_position_drift(
            TENANT_ID, SESSION_ID, "QQQ", "side_mismatch", 10.0, -10.0, "alerted"
        )
        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_POSITION_DRIFT
        assert event.severity == _E.NOTIFICATION_SEVERITY_CRITICAL
        assert event.extra["drift_type"] == "side_mismatch"

    async def test_on_position_drift_qty_is_not_critical(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_position_drift(
            TENANT_ID, SESSION_ID, "QQQ", "quantity_mismatch", 10.0, 11.0, "alerted"
        )
        assert _payload(_published(transport)[0]).severity == _E.NOTIFICATION_SEVERITY_UNSPECIFIED

    async def test_on_risk_breach_threads_details(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_risk_breach(
            TENANT_ID, SESSION_ID, "signal_rejected", {"symbol": "IWM", "violations": "max qty"}
        )
        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_RISK_BREACH
        assert event.symbol == "IWM"
        assert event.reason == "signal_rejected"

    async def test_loss_limits_map_to_risk_breach(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_daily_loss_limit(TENANT_ID, SESSION_ID, 500.0, 400.0)
        await service.on_drawdown_limit(TENANT_ID, SESSION_ID, 12.5, 10.0)
        events = [_payload(e) for e in _published(transport)]
        assert all(e.category == _E.NOTIFICATION_CATEGORY_RISK_BREACH for e in events)
        assert all(e.severity == _E.NOTIFICATION_SEVERITY_CRITICAL for e in events)

    async def test_on_strategy_error(self, service: AlertService, transport: FakeTransport) -> None:
        await service.on_strategy_error(TENANT_ID, SESSION_ID, "evaluation blew up")
        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_STRATEGY_ERROR
        assert event.reason == "evaluation blew up"

    async def test_session_lifecycle_events(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_session_started(TENANT_ID, SESSION_ID, "Recession Radar", "paper")
        await service.on_session_stopped(TENANT_ID, SESSION_ID, "user requested")
        await service.on_session_error(TENANT_ID, SESSION_ID, "runner crashed")
        categories = [_payload(e).category for e in _published(transport)]
        assert categories == [
            _E.NOTIFICATION_CATEGORY_SESSION_STARTED,
            _E.NOTIFICATION_CATEGORY_SESSION_STOPPED,
            _E.NOTIFICATION_CATEGORY_SESSION_ERROR,
        ]

    async def test_on_connection_lost(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_connection_lost(TENANT_ID, SESSION_ID, "trade_stream")
        event = _payload(_published(transport)[0])
        assert event.category == _E.NOTIFICATION_CATEGORY_CONNECTION_LOST
        assert event.extra["service"] == "trade_stream"

    async def test_circuit_breaker_events(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_circuit_breaker_triggered(
            TENANT_ID, SESSION_ID, "daily_loss", {"loss": 900.0}
        )
        await service.on_circuit_breaker_reset(TENANT_ID, SESSION_ID)
        events = [_payload(e) for e in _published(transport)]
        assert events[0].category == _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_TRIGGERED
        assert events[0].severity == _E.NOTIFICATION_SEVERITY_CRITICAL
        assert events[1].category == _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_RESET

    async def test_bracket_hits(self, service: AlertService, transport: FakeTransport) -> None:
        await service.on_stop_loss_hit(TENANT_ID, SESSION_ID, "SPY", 5.0, 490.0, 489.5)
        await service.on_take_profit_hit(TENANT_ID, SESSION_ID, "SPY", 5.0, 520.0, 520.5, 152.5)
        events = [_payload(e) for e in _published(transport)]
        assert events[0].category == _E.NOTIFICATION_CATEGORY_STOP_LOSS_HIT
        assert events[1].category == _E.NOTIFICATION_CATEGORY_TAKE_PROFIT_HIT
        assert events[1].extra["pnl"] == "152.5"


class TestDedupSemantics:
    async def test_repeated_stall_episode_collapses(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        for _ in range(2):
            await service.on_evaluation_stalled(TENANT_ID, SESSION_ID, ["SPY"], 700.0)
        ids = {e.id for e in _published(transport)}
        assert len(ids) == 1

    async def test_symbol_halt_dedups_per_symbol(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        await service.on_symbol_not_tradable(TENANT_ID, SESSION_ID, "ABC", "inactive", "halted")
        await service.on_symbol_not_tradable(TENANT_ID, SESSION_ID, "XYZ", "inactive", "halted")
        ids = {e.id for e in _published(transport)}
        assert len(ids) == 2

    async def test_order_fills_never_collapse(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        for _ in range(2):
            await service.on_order_rejected(TENANT_ID, SESSION_ID, "SPY", "buy", 1.0, "same")
        ids = {e.id for e in _published(transport)}
        assert len(ids) == 2

    async def test_sleeve_freeze_dedups_per_sleeve(
        self, service: AlertService, transport: FakeTransport
    ) -> None:
        sleeve = uuid4()
        for _ in range(2):
            await service.on_sleeve_frozen(TENANT_ID, sleeve, "drift")
        assert len({e.id for e in _published(transport)}) == 1


def test_get_alert_service_returns_publisher() -> None:
    assert isinstance(get_alert_service(), AlertService)
