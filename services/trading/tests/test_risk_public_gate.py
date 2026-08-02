"""Public risk-gate wiring: ``check_order(..., sleeve_id=...)`` end to end.

The sleeve checks (`_check_sleeve`) are unit-covered elsewhere; these tests
drive the PUBLIC entry point the executor calls, proving the sleeve gate is
actually wired into the violation flow: frozen sleeve → rejected, buys must fit
free cash (with the computed order value surfaced), fetch failures fail safe,
sells skip the cash check but are rejected when they exceed the sleeve's
holdings, and no sleeve_id skips the gate entirely.
"""

from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from llamatrade_proto.clients.ledger import LotInfo, SleeveCashInfo, SleeveDetail, SleeveInfo
from llamatrade_proto.generated.ledger_pb2 import (
    SLEEVE_STATUS_ACTIVE,
    SLEEVE_STATUS_FROZEN,
    SLEEVE_TYPE_STRATEGY,
)

from src.clients.portfolio_client import PortfolioLedgerClient
from src.models import RiskLimits
from src.risk.risk_manager import RiskManager

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
SLEEVE_ID = UUID("33333333-3333-3333-3333-333333333333")


class _FakePortfolioClient:
    """PortfolioLedgerClient double: canned sleeve detail or a fetch error."""

    def __init__(self, detail: SleeveDetail | None = None, error: Exception | None = None) -> None:
        self._detail = detail
        self._error = error
        self.calls = 0

    async def get_sleeve(self, tenant_id: UUID, user_id: str, sleeve_id: UUID) -> SleeveDetail:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._detail is not None
        return self._detail


def _lot(symbol: str = "SPY", qty: str = "100") -> LotInfo:
    return LotInfo(
        id=str(uuid4()),
        sleeve_id=str(SLEEVE_ID),
        symbol=symbol,
        side=1,
        qty=Decimal(qty),
        avg_price=Decimal("150"),
        cost_basis=Decimal(qty) * Decimal("150"),
        realized_pnl=Decimal("0"),
        is_open=True,
        opened_by_order_id="order-1",
    )


def _sleeve_detail(
    *,
    balance: str = "40000",
    reserved: str = "0",
    status: int = SLEEVE_STATUS_ACTIVE,
    lots: list[LotInfo] | None = None,
) -> SleeveDetail:
    return SleeveDetail(
        sleeve=SleeveInfo(
            id=str(SLEEVE_ID),
            tenant_id=str(TENANT_ID),
            account_id=str(ACCOUNT_ID),
            type=SLEEVE_TYPE_STRATEGY,
            status=status,
            name="Strategy A",
            strategy_execution_id=str(uuid4()),
            allocated_capital=Decimal("40000"),
            cash=SleeveCashInfo(
                balance=Decimal(balance), reserved=Decimal(reserved), unsettled=Decimal("0")
            ),
        ),
        lots=lots if lots is not None else [],
    )


def _risk_manager(client: _FakePortfolioClient) -> RiskManager:
    manager = RiskManager(portfolio_client=cast(PortfolioLedgerClient, client))
    manager._default_limits = RiskLimits(
        max_position_size=Decimal("100000"),
        max_daily_loss=Decimal("10000"),
        max_order_value=Decimal("50000"),
        allow_outside_market_hours=True,
    )
    return manager


class TestPublicRiskGateSleeveWiring:
    async def test_frozen_sleeve_rejects_order(self) -> None:
        client = _FakePortfolioClient(detail=_sleeve_detail(status=SLEEVE_STATUS_FROZEN))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is False
        assert any("frozen" in v for v in result.violations)
        assert client.calls == 1

    async def test_buy_exceeding_sleeve_free_cash_rejects_with_computed_value(self) -> None:
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="1000"))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is False
        # 10 × 150 = $1500.00 against $1000.00 free cash, surfaced verbatim.
        assert any("$1500.00" in v and "free cash $1000.00" in v for v in result.violations)

    async def test_reserved_cash_shrinks_buying_power(self) -> None:
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="2000", reserved="1500"))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("100"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is False
        assert any("free cash $500.00" in v for v in result.violations)

    async def test_sleeve_fetch_error_fails_safe(self) -> None:
        client = _FakePortfolioClient(error=ConnectionError("portfolio down"))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is False
        assert any("Unable to verify sleeve state" in v for v in result.violations)

    async def test_sell_within_holdings_bypasses_free_cash_check(self) -> None:
        # No free cash, but the sleeve holds the shares → the sell passes.
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="0", lots=[_lot(qty="100")]))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="sell",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is True
        assert result.violations == []
        assert client.calls == 1  # sleeve status + holdings verified on sells

    async def test_sell_exceeding_holdings_rejects(self) -> None:
        # F5: a sell the sleeve cannot cover is rejected pre-trade, not booked and frozen.
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="0", lots=[]))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="sell",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is False
        assert any("exceeds sleeve holdings" in v for v in result.violations)

    async def test_no_sleeve_id_skips_sleeve_checks_entirely(self) -> None:
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="0"))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
        )
        assert result.passed is True
        assert client.calls == 0

    async def test_within_free_cash_buy_passes(self) -> None:
        client = _FakePortfolioClient(detail=_sleeve_detail(balance="40000"))
        result = await _risk_manager(client).check_order(
            tenant_id=TENANT_ID,
            symbol="SPY",
            side="buy",
            qty=Decimal("10"),
            order_type="limit",
            limit_price=Decimal("150"),
            sleeve_id=SLEEVE_ID,
        )
        assert result.passed is True
        assert result.violations == []
