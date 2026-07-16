"""Tests for llamatrade_proto.clients.ledger module."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from llamatrade_proto.clients.ledger import (
    LedgerClient,
    SleeveCashInfo,
    _dec,
)
from llamatrade_proto.generated import common_pb2, ledger_pb2

TENANT = "tenant-123"
USER = "user-456"


def _pb_sleeve(
    sleeve_id: str = "sleeve-1",
    balance: str = "40000",
    reserved: str = "0",
) -> ledger_pb2.Sleeve:
    return ledger_pb2.Sleeve(
        id=sleeve_id,
        tenant_id=TENANT,
        account_id="account-1",
        type=ledger_pb2.SLEEVE_TYPE_STRATEGY,
        status=ledger_pb2.SLEEVE_STATUS_ACTIVE,
        name="Strategy A",
        strategy_execution_id="exec-1",
        allocated_capital=common_pb2.Decimal(value="40000"),
        cash=ledger_pb2.SleeveCash(
            balance=common_pb2.Decimal(value=balance),
            reserved=common_pb2.Decimal(value=reserved),
            unsettled=common_pb2.Decimal(value="0"),
        ),
    )


class TestDecHelper:
    """Tests for proto Decimal conversion."""

    def test_parses_value(self) -> None:
        assert _dec(common_pb2.Decimal(value="480.25")) == Decimal("480.25")

    def test_empty_value_defaults_to_zero(self) -> None:
        assert _dec(common_pb2.Decimal()) == Decimal("0")


class TestSleeveCashInfo:
    """Tests for SleeveCashInfo dataclass."""

    def test_free_is_balance_minus_reserved(self) -> None:
        cash = SleeveCashInfo(
            balance=Decimal("1000"), reserved=Decimal("250"), unsettled=Decimal("0")
        )
        assert cash.free == Decimal("750")

    def test_free_zero_reserved(self) -> None:
        cash = SleeveCashInfo(
            balance=Decimal("1000"), reserved=Decimal("0"), unsettled=Decimal("0")
        )
        assert cash.free == Decimal("1000")


class TestLedgerClientInit:
    """Tests for LedgerClient initialization."""

    def test_init_with_defaults(self) -> None:
        client = LedgerClient()
        assert client.target == "http://portfolio:8860"
        assert client._client is None

    def test_init_with_custom_target(self) -> None:
        client = LedgerClient("localhost:9000")
        assert client.target == "http://localhost:9000"


class TestGetOrCreateAccount:
    """Tests for LedgerClient.get_or_create_account."""

    @pytest.mark.asyncio
    async def test_returns_account_and_base_sleeves(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.GetOrCreateAccountResponse(
            account=ledger_pb2.LedgerAccount(
                id="account-1",
                tenant_id=TENANT,
                credentials_id="creds-1",
                base_currency="USD",
            ),
            base_sleeves=[
                _pb_sleeve("sleeve-unalloc"),
                _pb_sleeve("sleeve-manual"),
                _pb_sleeve("sleeve-unmanaged"),
            ],
        )
        mock_client = MagicMock()
        mock_client.get_or_create_account = AsyncMock(return_value=response)
        client._client = mock_client

        result = await client.get_or_create_account(TENANT, USER, "creds-1")

        assert result.account.id == "account-1"
        assert result.account.credentials_id == "creds-1"
        assert [s.id for s in result.base_sleeves] == [
            "sleeve-unalloc",
            "sleeve-manual",
            "sleeve-unmanaged",
        ]
        request = mock_client.get_or_create_account.call_args[0][0]
        assert request.credentials_id == "creds-1"
        assert request.context.tenant_id == TENANT
        assert request.context.user_id == USER

    @pytest.mark.asyncio
    async def test_missing_base_currency_defaults_usd(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.GetOrCreateAccountResponse(
            account=ledger_pb2.LedgerAccount(id="account-1", tenant_id=TENANT)
        )
        mock_client = MagicMock()
        mock_client.get_or_create_account = AsyncMock(return_value=response)
        client._client = mock_client

        result = await client.get_or_create_account(TENANT, USER, "creds-1")

        assert result.account.base_currency == "USD"
        assert result.base_sleeves == []


class TestAllocateCapital:
    """Tests for LedgerClient.allocate_capital."""

    @pytest.mark.asyncio
    async def test_sends_amount_and_parses_sleeve(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.AllocateCapitalResponse(sleeve=_pb_sleeve())
        mock_client = MagicMock()
        mock_client.allocate_capital = AsyncMock(return_value=response)
        client._client = mock_client

        sleeve = await client.allocate_capital(
            TENANT, USER, "account-1", "sleeve-1", Decimal("40000")
        )

        assert sleeve.id == "sleeve-1"
        assert sleeve.allocated_capital == Decimal("40000")
        assert sleeve.cash.balance == Decimal("40000")
        assert sleeve.cash.free == Decimal("40000")
        request = mock_client.allocate_capital.call_args[0][0]
        assert request.account_id == "account-1"
        assert request.to_sleeve_id == "sleeve-1"
        assert request.amount.value == "40000"

    @pytest.mark.asyncio
    async def test_rpc_error_propagates(self) -> None:
        client = LedgerClient()
        mock_client = MagicMock()
        mock_client.allocate_capital = AsyncMock(side_effect=RuntimeError("unavailable"))
        client._client = mock_client

        with pytest.raises(RuntimeError, match="unavailable"):
            await client.allocate_capital(TENANT, USER, "account-1", "sleeve-1", Decimal("1"))


class TestTransferCapital:
    """Tests for LedgerClient.transfer_capital."""

    @pytest.mark.asyncio
    async def test_returns_both_sleeves(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.TransferCapitalResponse(
            from_sleeve=_pb_sleeve("sleeve-from", balance="10000"),
            to_sleeve=_pb_sleeve("sleeve-to", balance="30000"),
        )
        mock_client = MagicMock()
        mock_client.transfer_capital = AsyncMock(return_value=response)
        client._client = mock_client

        from_sleeve, to_sleeve = await client.transfer_capital(
            TENANT, USER, "account-1", "sleeve-from", "sleeve-to", Decimal("30000")
        )

        assert from_sleeve.id == "sleeve-from"
        assert from_sleeve.cash.balance == Decimal("10000")
        assert to_sleeve.id == "sleeve-to"
        assert to_sleeve.cash.balance == Decimal("30000")


class TestFundOps:
    """Tests for deposit_funds / withdraw_funds."""

    @pytest.mark.asyncio
    async def test_deposit_returns_unallocated(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.DepositFundsResponse(
            unallocated=_pb_sleeve("sleeve-unalloc", balance="100000")
        )
        mock_client = MagicMock()
        mock_client.deposit_funds = AsyncMock(return_value=response)
        client._client = mock_client

        sleeve = await client.deposit_funds(TENANT, USER, "account-1", Decimal("100000"))

        assert sleeve.cash.balance == Decimal("100000")
        assert mock_client.deposit_funds.call_args[0][0].amount.value == "100000"

    @pytest.mark.asyncio
    async def test_withdraw_returns_unallocated(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.WithdrawFundsResponse(
            unallocated=_pb_sleeve("sleeve-unalloc", balance="60000")
        )
        mock_client = MagicMock()
        mock_client.withdraw_funds = AsyncMock(return_value=response)
        client._client = mock_client

        sleeve = await client.withdraw_funds(TENANT, USER, "account-1", Decimal("40000"))

        assert sleeve.cash.balance == Decimal("60000")


class TestSleeveQueries:
    """Tests for list_sleeves / get_sleeve."""

    @pytest.mark.asyncio
    async def test_list_sleeves(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.ListSleevesResponse(
            sleeves=[_pb_sleeve("sleeve-1"), _pb_sleeve("sleeve-2")]
        )
        mock_client = MagicMock()
        mock_client.list_sleeves = AsyncMock(return_value=response)
        client._client = mock_client

        sleeves = await client.list_sleeves(TENANT, USER, "account-1")

        assert [s.id for s in sleeves] == ["sleeve-1", "sleeve-2"]

    @pytest.mark.asyncio
    async def test_get_sleeve_with_lots_and_reserved_cash(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.GetSleeveResponse(
            sleeve=_pb_sleeve(balance="40000", reserved="9600"),
            lots=[
                ledger_pb2.Lot(
                    id="lot-1",
                    sleeve_id="sleeve-1",
                    symbol="SPY",
                    side=ledger_pb2.LOT_SIDE_LONG,
                    qty=common_pb2.Decimal(value="83"),
                    avg_price=common_pb2.Decimal(value="480"),
                    cost_basis=common_pb2.Decimal(value="39840"),
                    realized_pnl=common_pb2.Decimal(value="0"),
                    is_open=True,
                    opened_by_order_id="order-1",
                )
            ],
        )
        mock_client = MagicMock()
        mock_client.get_sleeve = AsyncMock(return_value=response)
        client._client = mock_client

        detail = await client.get_sleeve(TENANT, USER, "sleeve-1")

        assert detail.sleeve.cash.free == Decimal("30400")
        assert len(detail.lots) == 1
        lot = detail.lots[0]
        assert lot.symbol == "SPY"
        assert lot.qty == Decimal("83")
        assert lot.cost_basis == Decimal("39840")
        assert lot.is_open is True


class TestHoldingHistory:
    """Tests for get_holding_history."""

    @pytest.mark.asyncio
    async def test_parses_entries(self) -> None:
        client = LedgerClient()
        response = ledger_pb2.GetHoldingHistoryResponse(
            entries=[
                ledger_pb2.HoldingHistoryEntry(
                    occurred_at=common_pb2.Timestamp(seconds=1765476600),
                    sleeve_id="sleeve-1",
                    source=ledger_pb2.SLEEVE_TYPE_STRATEGY,
                    strategy_execution_id="exec-1",
                    side="buy",
                    qty=common_pb2.Decimal(value="83"),
                    price=common_pb2.Decimal(value="480"),
                    realized_pnl=common_pb2.Decimal(),
                    order_id="order-1",
                )
            ]
        )
        mock_client = MagicMock()
        mock_client.get_holding_history = AsyncMock(return_value=response)
        client._client = mock_client

        entries = await client.get_holding_history(TENANT, USER, "account-1", "SPY")

        assert len(entries) == 1
        entry = entries[0]
        assert entry.sleeve_id == "sleeve-1"
        assert entry.side == "buy"
        assert entry.qty == Decimal("83")
        assert entry.realized_pnl == Decimal("0")
        assert entry.occurred_at_seconds == 1765476600
        request = mock_client.get_holding_history.call_args[0][0]
        assert request.symbol == "SPY"
