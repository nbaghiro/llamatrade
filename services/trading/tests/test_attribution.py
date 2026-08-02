"""Shared order-attribution resolution + terminal-emission backfill tests.

Covers ``src.attribution.resolve_order_attribution`` (the single resolver behind
SubmitOrder and recovery emission) and the executor's ``_emit_ledger_for_terminal``
backfill: an unattributed terminal order resolves the account's Manual sleeve and
emits; a resolution failure logs and skips without raising.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.ledger_pb2 import (
    SLEEVE_TYPE_MANUAL,
    SLEEVE_TYPE_UNALLOCATED,
    SLEEVE_TYPE_UNMANAGED,
)
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_FILLED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.attribution import resolve_order_attribution
from src.executor.order_executor import OrderExecutor

pytestmark = pytest.mark.asyncio

TENANT_ID = uuid4()
SESSION_ID = uuid4()
CREATED_BY = uuid4()


def _session_row(*, sleeve_id=None, account_id=None):
    return SimpleNamespace(
        id=SESSION_ID,
        tenant_id=TENANT_ID,
        sleeve_id=sleeve_id,
        account_id=account_id,
        credentials_id=uuid4(),
        created_by=CREATED_BY,
    )


def _bootstrap(manual_sleeve_id, account_id):
    return SimpleNamespace(
        account=SimpleNamespace(id=str(account_id)),
        base_sleeves=[
            SimpleNamespace(id=str(uuid4()), type=SLEEVE_TYPE_UNALLOCATED),
            SimpleNamespace(id=str(manual_sleeve_id), type=SLEEVE_TYPE_MANUAL),
        ],
    )


# --------------------------------------------------------------------------- #
# resolve_order_attribution
# --------------------------------------------------------------------------- #


async def test_resolver_prefers_session_sleeve_without_ledger_call():
    sleeve_id, account_id = uuid4(), uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=_session_row(sleeve_id=sleeve_id, account_id=account_id))
    ledger = AsyncMock()

    resolved = await resolve_order_attribution(
        db=db, ledger=ledger, tenant_id=TENANT_ID, session_id=SESSION_ID, requested_sleeve_id=""
    )

    assert resolved == (sleeve_id, account_id)
    ledger.get_or_create_account.assert_not_called()


async def test_resolver_falls_back_to_manual_sleeve_with_session_creator_identity():
    """No user_id supplied (recovery path) → the session creator's identity is used."""
    manual_id, account_id = uuid4(), uuid4()
    session = _session_row()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=session)
    ledger = AsyncMock()
    ledger.get_or_create_account = AsyncMock(return_value=_bootstrap(manual_id, account_id))

    resolved = await resolve_order_attribution(
        db=db, ledger=ledger, tenant_id=TENANT_ID, session_id=SESSION_ID, requested_sleeve_id=""
    )

    assert resolved == (manual_id, account_id)
    ledger.get_or_create_account.assert_awaited_once_with(
        str(TENANT_ID), str(CREATED_BY), str(session.credentials_id)
    )


async def test_resolver_explicit_user_id_overrides_session_creator():
    manual_id, account_id = uuid4(), uuid4()
    user_id = str(uuid4())
    session = _session_row()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=session)
    ledger = AsyncMock()
    ledger.get_or_create_account = AsyncMock(return_value=_bootstrap(manual_id, account_id))

    await resolve_order_attribution(
        db=db,
        ledger=ledger,
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        requested_sleeve_id="",
        user_id=user_id,
    )

    ledger.get_or_create_account.assert_awaited_once_with(
        str(TENANT_ID), user_id, str(session.credentials_id)
    )


async def test_resolver_ignores_caller_supplied_sleeve_id():
    """The public order path never trusts a caller sleeve_id — it derives from the session."""
    session_sleeve, account_id, requested = uuid4(), uuid4(), uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(
        return_value=_session_row(sleeve_id=session_sleeve, account_id=account_id)
    )
    ledger = AsyncMock()

    resolved = await resolve_order_attribution(
        db=db,
        ledger=ledger,
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        requested_sleeve_id=str(requested),
    )

    # Session's own sleeve wins; the caller-supplied sleeve is never returned.
    assert resolved == (session_sleeve, account_id)
    assert resolved[0] != requested
    ledger.get_sleeve.assert_not_called()


async def test_resolver_routes_unheld_sell_to_unmanaged():
    """A sell of a symbol the Manual sleeve doesn't hold books to Unmanaged (F5)."""
    manual_id, unmanaged_id, account_id = uuid4(), uuid4(), uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=_session_row())
    ledger = AsyncMock()
    ledger.get_or_create_account = AsyncMock(
        return_value=SimpleNamespace(
            account=SimpleNamespace(id=str(account_id)),
            base_sleeves=[
                SimpleNamespace(id=str(manual_id), type=SLEEVE_TYPE_MANUAL),
                SimpleNamespace(id=str(unmanaged_id), type=SLEEVE_TYPE_UNMANAGED),
            ],
        )
    )

    def _detail(*args, **kwargs):
        sleeve_id = args[2]
        lot_symbol = "AAPL" if sleeve_id == str(unmanaged_id) else "NONE"
        return SimpleNamespace(
            lots=[SimpleNamespace(symbol=lot_symbol, qty=Decimal("100"), is_open=True)]
        )

    ledger.get_sleeve = AsyncMock(side_effect=_detail)

    resolved = await resolve_order_attribution(
        db=db,
        ledger=ledger,
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        requested_sleeve_id="",
        symbol="AAPL",
        side="sell",
    )

    assert resolved == (unmanaged_id, account_id)


async def test_resolver_buy_fallback_stays_manual():
    """A buy fallback books to Manual and never inspects lots."""
    manual_id, unmanaged_id, account_id = uuid4(), uuid4(), uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=_session_row())
    ledger = AsyncMock()
    ledger.get_or_create_account = AsyncMock(
        return_value=SimpleNamespace(
            account=SimpleNamespace(id=str(account_id)),
            base_sleeves=[
                SimpleNamespace(id=str(manual_id), type=SLEEVE_TYPE_MANUAL),
                SimpleNamespace(id=str(unmanaged_id), type=SLEEVE_TYPE_UNMANAGED),
            ],
        )
    )

    resolved = await resolve_order_attribution(
        db=db,
        ledger=ledger,
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        requested_sleeve_id="",
        symbol="AAPL",
        side="buy",
    )

    assert resolved == (manual_id, account_id)
    ledger.get_sleeve.assert_not_called()


async def test_resolver_unresolvable_returns_none_pair():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)  # session not found
    ledger = AsyncMock()

    resolved = await resolve_order_attribution(
        db=db, ledger=ledger, tenant_id=TENANT_ID, session_id=SESSION_ID, requested_sleeve_id=""
    )

    assert resolved == (None, None)
    ledger.get_or_create_account.assert_not_called()


# --------------------------------------------------------------------------- #
# _emit_ledger_for_terminal backfill
# --------------------------------------------------------------------------- #


def _terminal_order() -> Order:
    o = Order(
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        client_order_id="lt-unattributed",
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("10"),
        status=ORDER_STATUS_FILLED,
        filled_qty=Decimal("10"),
    )
    o.id = uuid4()
    o.sleeve_id = None
    o.account_id = None
    o.filled_avg_price = Decimal("150")
    o.filled_at = datetime.now(UTC)
    o.created_at = datetime.now(UTC)
    return o


def _executor(mock_db, mock_alpaca_client, mock_risk_manager) -> tuple[OrderExecutor, MagicMock]:
    publisher = MagicMock()
    publisher.publish_ledger_fill = AsyncMock()
    executor = OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=None,
        event_publisher=publisher,
    )
    return executor, publisher


async def test_emit_backfills_manual_sleeve_and_emits(
    mock_db, mock_alpaca_client, mock_risk_manager
):
    executor, publisher = _executor(mock_db, mock_alpaca_client, mock_risk_manager)
    order = _terminal_order()
    sleeve_id, account_id = uuid4(), uuid4()

    with (
        patch(
            "src.attribution.resolve_order_attribution",
            new=AsyncMock(return_value=(sleeve_id, account_id)),
        ),
        patch("src.attribution.get_ledger_client", new=MagicMock()),
    ):
        await executor._emit_ledger_for_terminal(order)

    assert order.sleeve_id == sleeve_id
    assert order.account_id == account_id
    mock_db.commit.assert_awaited()  # resolved attribution persisted onto the row
    publisher.publish_ledger_fill.assert_awaited()


async def test_emit_skips_with_warning_when_resolution_fails(
    mock_db, mock_alpaca_client, mock_risk_manager, caplog
):
    executor, publisher = _executor(mock_db, mock_alpaca_client, mock_risk_manager)
    order = _terminal_order()

    with (
        patch(
            "src.attribution.resolve_order_attribution",
            new=AsyncMock(side_effect=RuntimeError("ledger down")),
        ),
        patch("src.attribution.get_ledger_client", new=MagicMock()),
        caplog.at_level("WARNING"),
    ):
        await executor._emit_ledger_for_terminal(order)  # must not raise

    assert order.sleeve_id is None
    publisher.publish_ledger_fill.assert_not_awaited()
    assert any("Attribution resolution failed" in r.message for r in caplog.records)


async def test_emit_skips_with_warning_when_unresolvable(
    mock_db, mock_alpaca_client, mock_risk_manager, caplog
):
    executor, publisher = _executor(mock_db, mock_alpaca_client, mock_risk_manager)
    order = _terminal_order()

    with (
        patch(
            "src.attribution.resolve_order_attribution",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch("src.attribution.get_ledger_client", new=MagicMock()),
        caplog.at_level("WARNING"),
    ):
        await executor._emit_ledger_for_terminal(order)

    publisher.publish_ledger_fill.assert_not_awaited()
    mock_db.commit.assert_not_awaited()
    assert any("No resolvable sleeve" in r.message for r in caplog.records)


async def test_emit_still_noop_without_publisher(mock_db, mock_alpaca_client, mock_risk_manager):
    executor = OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=None,
        event_publisher=None,
    )
    with patch("src.attribution.resolve_order_attribution", new=AsyncMock()) as resolve:
        await executor._emit_ledger_for_terminal(_terminal_order())
    resolve.assert_not_called()
