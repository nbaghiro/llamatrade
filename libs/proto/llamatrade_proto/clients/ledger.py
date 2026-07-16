"""Ledger client (LedgerService, hosted by the portfolio service).

Consumed by the strategy service (GetOrCreateAccount + AllocateCapital when an
execution is funded) and the trading service (GetSleeve for sleeve equity /
free cash, Manual-sleeve resolution for unattributed orders).

The portfolio service serves LedgerService as a Connect ASGI app (HTTP/1.1), so
callers use the generated Connect client — not a native-gRPC channel. Inter-service
calls carry a minted service token so they pass portfolio's fail-closed auth.

Unlike validation-style clients, fund operations are mutations: RPC errors
propagate as ``connectrpc.errors.ConnectError`` so callers can handle them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from llamatrade_common.auth import mint_service_token
from llamatrade_proto.generated.ledger_connect import LedgerServiceClient

if TYPE_CHECKING:
    from llamatrade_proto.generated import ledger_pb2

logger = logging.getLogger(__name__)


def _normalize_target(target: str) -> str:
    """Connect needs an absolute URL; accept bare ``host:port`` too."""
    if target.startswith(("http://", "https://")):
        return target
    return f"http://{target}"


@dataclass
class LedgerAccountInfo:
    """A ledger account (one per broker credential set)."""

    id: str
    tenant_id: str
    credentials_id: str
    base_currency: str


@dataclass
class SleeveCashInfo:
    """Per-sleeve cash sub-ledger."""

    balance: Decimal
    reserved: Decimal
    unsettled: Decimal

    @property
    def free(self) -> Decimal:
        """Spendable cash: balance minus cash earmarked for open buy orders."""
        return self.balance - self.reserved


@dataclass
class SleeveInfo:
    """A virtual sub-portfolio within an account."""

    id: str
    tenant_id: str
    account_id: str
    type: int  # proto SleeveType value
    status: int  # proto SleeveStatus value
    name: str
    strategy_execution_id: str
    allocated_capital: Decimal
    cash: SleeveCashInfo
    realized_pnl: Decimal = Decimal("0")


@dataclass
class LotInfo:
    """A provenance-bearing unit of a holding owned by one sleeve."""

    id: str
    sleeve_id: str
    symbol: str
    side: int  # proto LotSide value
    qty: Decimal
    avg_price: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    is_open: bool
    opened_by_order_id: str


@dataclass
class HoldingHistoryEntryInfo:
    """One entry in a per-symbol provenance timeline."""

    sleeve_id: str
    source: int  # proto SleeveType value
    strategy_execution_id: str
    side: str
    qty: Decimal
    price: Decimal
    realized_pnl: Decimal
    order_id: str
    occurred_at_seconds: int


@dataclass
class AccountBootstrapResult:
    """Result of GetOrCreateAccount: the account plus its base sleeves."""

    account: LedgerAccountInfo
    base_sleeves: list[SleeveInfo] = field(default_factory=list)


@dataclass
class SleeveDetail:
    """Result of GetSleeve: the sleeve plus its open lots."""

    sleeve: SleeveInfo
    lots: list[LotInfo] = field(default_factory=list)


@dataclass
class RehomedPositionInfo:
    """A position moved out of a closing sleeve (into Unmanaged), at cost."""

    symbol: str
    qty: Decimal
    cost_basis: Decimal


@dataclass
class SleeveCloseInfo:
    """Result of CloseSleeve: the now-CLOSED sleeve plus what it re-homed."""

    sleeve: SleeveInfo
    already_closed: bool
    rehomed_cash: Decimal
    rehomed_positions: list[RehomedPositionInfo] = field(default_factory=list)


def _dec(pb_value: object) -> Decimal:
    """Convert a proto Decimal (string-valued) to a Decimal, defaulting to 0."""
    raw = getattr(pb_value, "value", "")
    return Decimal(raw) if raw else Decimal("0")


class LedgerClient:
    """Connect client for the LedgerService API (served by portfolio, port 8860).

    Example:
        ledger = LedgerClient("portfolio:8860", service_name="strategy")
        result = await ledger.get_or_create_account(tenant_id, user_id, credentials_id)
        sleeve = await ledger.allocate_capital(
            tenant_id, user_id, result.account.id, sleeve_id, Decimal("40000")
        )
    """

    def __init__(self, target: str = "portfolio:8860", *, service_name: str = "internal") -> None:
        self.target = _normalize_target(target)
        self._service_name = service_name
        self._client: LedgerServiceClient | None = None

    def _get_client(self) -> LedgerServiceClient:
        if self._client is None:
            self._client = LedgerServiceClient(self.target)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Internal service token so the call clears portfolio's fail-closed auth."""
        return {"Authorization": f"Bearer {mint_service_token(service_name=self._service_name)}"}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> LedgerClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def get_or_create_account(
        self, tenant_id: str, user_id: str, credentials_id: str
    ) -> AccountBootstrapResult:
        """Resolve (lazily creating) the Account for a broker credential set."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.GetOrCreateAccountRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            credentials_id=credentials_id,
        )
        response = await self._get_client().get_or_create_account(request, headers=self._headers())
        return AccountBootstrapResult(
            account=self._to_account(response.account),
            base_sleeves=[self._to_sleeve(s) for s in response.base_sleeves],
        )

    async def allocate_capital(
        self,
        tenant_id: str,
        user_id: str,
        account_id: str,
        to_sleeve_id: str,
        amount: Decimal,
        *,
        strategy_execution_id: str = "",
        sleeve_name: str = "",
    ) -> SleeveInfo:
        """Move free cash from the Unallocated sleeve into a target sleeve.

        Open-and-fund: with an empty ``to_sleeve_id`` and a
        ``strategy_execution_id``, the portfolio opens (or reuses) the strategy
        sleeve linked to that execution and funds it in one call.
        """
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.AllocateCapitalRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            to_sleeve_id=to_sleeve_id,
            amount=common_pb2.Decimal(value=str(amount)),
            strategy_execution_id=strategy_execution_id,
            sleeve_name=sleeve_name,
        )
        response = await self._get_client().allocate_capital(request, headers=self._headers())
        return self._to_sleeve(response.sleeve)

    async def transfer_capital(
        self,
        tenant_id: str,
        user_id: str,
        account_id: str,
        from_sleeve_id: str,
        to_sleeve_id: str,
        amount: Decimal,
    ) -> tuple[SleeveInfo, SleeveInfo]:
        """Move free cash between two sleeves; returns (from_sleeve, to_sleeve)."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.TransferCapitalRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            from_sleeve_id=from_sleeve_id,
            to_sleeve_id=to_sleeve_id,
            amount=common_pb2.Decimal(value=str(amount)),
        )
        response = await self._get_client().transfer_capital(request, headers=self._headers())
        return self._to_sleeve(response.from_sleeve), self._to_sleeve(response.to_sleeve)

    async def close_sleeve(
        self,
        tenant_id: str,
        user_id: str,
        account_id: str,
        sleeve_id: str,
        *,
        reason: str = "",
    ) -> SleeveCloseInfo:
        """Close (retire) a sleeve: re-home its open positions → Unmanaged and
        free cash → Unallocated, then mark it CLOSED. Idempotent — a re-close of
        an already-closed sleeve is a no-op (``already_closed`` is True)."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.CloseSleeveRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            sleeve_id=sleeve_id,
            reason=reason,
        )
        response = await self._get_client().close_sleeve(request, headers=self._headers())
        return SleeveCloseInfo(
            sleeve=self._to_sleeve(response.sleeve),
            already_closed=response.already_closed,
            rehomed_cash=_dec(response.rehomed_cash),
            rehomed_positions=[
                RehomedPositionInfo(symbol=p.symbol, qty=_dec(p.qty), cost_basis=_dec(p.cost_basis))
                for p in response.rehomed_positions
            ],
        )

    async def deposit_funds(
        self, tenant_id: str, user_id: str, account_id: str, amount: Decimal
    ) -> SleeveInfo:
        """Record external cash entering the account (credited to Unallocated)."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.DepositFundsRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            amount=common_pb2.Decimal(value=str(amount)),
        )
        response = await self._get_client().deposit_funds(request, headers=self._headers())
        return self._to_sleeve(response.unallocated)

    async def withdraw_funds(
        self, tenant_id: str, user_id: str, account_id: str, amount: Decimal
    ) -> SleeveInfo:
        """Record external cash leaving the account (debited from Unallocated)."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.WithdrawFundsRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            amount=common_pb2.Decimal(value=str(amount)),
        )
        response = await self._get_client().withdraw_funds(request, headers=self._headers())
        return self._to_sleeve(response.unallocated)

    async def list_sleeves(self, tenant_id: str, user_id: str, account_id: str) -> list[SleeveInfo]:
        """List all sleeves in an account."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.ListSleevesRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
        )
        response = await self._get_client().list_sleeves(request, headers=self._headers())
        return [self._to_sleeve(s) for s in response.sleeves]

    async def get_sleeve(self, tenant_id: str, user_id: str, sleeve_id: str) -> SleeveDetail:
        """Fetch one sleeve with its open lots (projection-backed)."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.GetSleeveRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            sleeve_id=sleeve_id,
        )
        response = await self._get_client().get_sleeve(request, headers=self._headers())
        return SleeveDetail(
            sleeve=self._to_sleeve(response.sleeve),
            lots=[self._to_lot(lot) for lot in response.lots],
        )

    async def get_holding_history(
        self, tenant_id: str, user_id: str, account_id: str, symbol: str
    ) -> list[HoldingHistoryEntryInfo]:
        """Per-symbol provenance timeline across all sleeves in an account."""
        from llamatrade_proto.generated import common_pb2, ledger_pb2

        request = ledger_pb2.GetHoldingHistoryRequest(
            context=common_pb2.TenantContext(tenant_id=tenant_id, user_id=user_id),
            account_id=account_id,
            symbol=symbol,
        )
        response = await self._get_client().get_holding_history(request, headers=self._headers())
        return [
            HoldingHistoryEntryInfo(
                sleeve_id=entry.sleeve_id,
                source=entry.source,
                strategy_execution_id=entry.strategy_execution_id,
                side=entry.side,
                qty=_dec(entry.qty),
                price=_dec(entry.price),
                realized_pnl=_dec(entry.realized_pnl),
                order_id=entry.order_id,
                occurred_at_seconds=entry.occurred_at.seconds,
            )
            for entry in response.entries
        ]

    @staticmethod
    def _to_account(pb: ledger_pb2.LedgerAccount) -> LedgerAccountInfo:
        return LedgerAccountInfo(
            id=pb.id,
            tenant_id=pb.tenant_id,
            credentials_id=pb.credentials_id,
            base_currency=pb.base_currency or "USD",
        )

    @staticmethod
    def _to_sleeve(pb: ledger_pb2.Sleeve) -> SleeveInfo:
        return SleeveInfo(
            id=pb.id,
            tenant_id=pb.tenant_id,
            account_id=pb.account_id,
            type=pb.type,
            status=pb.status,
            name=pb.name,
            strategy_execution_id=pb.strategy_execution_id,
            allocated_capital=_dec(pb.allocated_capital),
            cash=SleeveCashInfo(
                balance=_dec(pb.cash.balance),
                reserved=_dec(pb.cash.reserved),
                unsettled=_dec(pb.cash.unsettled),
            ),
            realized_pnl=_dec(pb.realized_pnl),
        )

    @staticmethod
    def _to_lot(pb: ledger_pb2.Lot) -> LotInfo:
        return LotInfo(
            id=pb.id,
            sleeve_id=pb.sleeve_id,
            symbol=pb.symbol,
            side=pb.side,
            qty=_dec(pb.qty),
            avg_price=_dec(pb.avg_price),
            cost_basis=_dec(pb.cost_basis),
            realized_pnl=_dec(pb.realized_pnl),
            is_open=pb.is_open,
            opened_by_order_id=pb.opened_by_order_id,
        )
