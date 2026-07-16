"""Connect servicer for the LedgerService (hosted by the portfolio process).

Fund disbursement (allocate/transfer/deposit/withdraw) goes through
``FundService``; sleeve/holding queries read projections via ``LedgerProjector``.
All balances are projected from the event log — the book of record.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import get_session_maker
from llamatrade_proto.generated import common_pb2, ledger_pb2

from src.ledger.funds import FundError
from src.ledger.lifecycle import SleeveCloseError
from src.ledger.projection import HoldingHistoryEntry
from src.ledger.projector import LedgerProjector
from src.repositories import SqlLedgerStore, SqlSleeveRepository
from src.services.fund_service import FundService, SleeveView
from src.services.sleeve_lifecycle_service import SleeveLifecycleService
from src.services.sleeve_service import SleeveService

if TYPE_CHECKING:
    from llamatrade_db.models.ledger import Account, Sleeve

logger = logging.getLogger(__name__)

type AnyContext = RequestContext[object, object]

_TYPE_TO_PROTO = {
    "strategy": ledger_pb2.SLEEVE_TYPE_STRATEGY,
    "manual": ledger_pb2.SLEEVE_TYPE_MANUAL,
    "unmanaged": ledger_pb2.SLEEVE_TYPE_UNMANAGED,
    "unallocated": ledger_pb2.SLEEVE_TYPE_UNALLOCATED,
}
_STATUS_TO_PROTO = {
    "active": ledger_pb2.SLEEVE_STATUS_ACTIVE,
    "frozen": ledger_pb2.SLEEVE_STATUS_FROZEN,
    "closed": ledger_pb2.SLEEVE_STATUS_CLOSED,
}


def _dec(value: object) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=str(value))


def _amount(value: common_pb2.Decimal) -> Decimal:
    return Decimal(value.value or "0")


def _sleeve_to_proto(
    sleeve: Sleeve,
    cash: Decimal,
    reserved: Decimal | None = None,
    realized_pnl: Decimal | None = None,
) -> ledger_pb2.Sleeve:
    return ledger_pb2.Sleeve(
        id=str(sleeve.id),
        tenant_id=str(sleeve.tenant_id),
        account_id=str(sleeve.account_id),
        type=_TYPE_TO_PROTO.get(sleeve.type, ledger_pb2.SLEEVE_TYPE_UNSPECIFIED),
        status=_STATUS_TO_PROTO.get(sleeve.status, ledger_pb2.SLEEVE_STATUS_UNSPECIFIED),
        name=sleeve.name,
        strategy_execution_id=(
            str(sleeve.strategy_execution_id) if sleeve.strategy_execution_id else ""
        ),
        allocated_capital=_dec(sleeve.allocated_capital),
        cash=ledger_pb2.SleeveCash(
            balance=_dec(cash),
            # All cash state is projected from the event log; default to 0 when a
            # caller builds the proto without the projected reservation total.
            reserved=_dec(reserved if reserved is not None else 0),
            unsettled=_dec(0),  # settlement tracking not modeled yet
        ),
        realized_pnl=_dec(realized_pnl if realized_pnl is not None else Decimal("0")),
    )


def _view_to_proto(view: SleeveView) -> ledger_pb2.Sleeve:
    return _sleeve_to_proto(view.sleeve, view.cash)


def _account_to_proto(account: Account) -> ledger_pb2.LedgerAccount:
    return ledger_pb2.LedgerAccount(
        id=str(account.id),
        tenant_id=str(account.tenant_id),
        credentials_id=str(account.credentials_id),
        base_currency=account.base_currency,
    )


class LedgerServicer:
    """Connect servicer for ``LedgerService`` (port 8860, portfolio process)."""

    def __init__(self) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _get_db(self) -> AsyncSession:
        if self._session_factory is None:
            self._session_factory = get_session_maker()
        return self._session_factory()

    async def get_or_create_account(
        self, request: ledger_pb2.GetOrCreateAccountRequest, ctx: AnyContext
    ) -> ledger_pb2.GetOrCreateAccountResponse:
        """Resolve (lazily creating) the Account for a broker credential set.

        Idempotent: also ensures the singleton base sleeves exist. First-time
        creation seeds the ledger from current broker state (cash →
        Unallocated, pre-existing positions → Unmanaged) so the
        ``Σ sleeves == broker`` invariant holds from day one. Backfill is
        best-effort: a broker outage logs and proceeds — re-onboarding is
        idempotent and reconciliation surfaces the gap until then.
        """
        tenant_id = UUID(request.context.tenant_id)
        try:
            credentials_id = UUID(request.credentials_id)
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, "credentials_id must be a UUID") from e
        try:
            async with self._get_db() as db:
                repo = SqlSleeveRepository(db)
                sleeves = SleeveService(repo)
                existed = (
                    await repo.get_account_by_credentials(tenant_id, credentials_id) is not None
                )
                account = await sleeves.get_or_create_account(tenant_id, credentials_id)
                base = await sleeves.ensure_base_sleeves(account)
                if not existed:
                    await self._backfill_account(db, sleeves, tenant_id, credentials_id)
                projection = await LedgerProjector(db).project_account(tenant_id, account.id)
                await db.commit()
                return ledger_pb2.GetOrCreateAccountResponse(
                    account=_account_to_proto(account),
                    base_sleeves=[
                        _sleeve_to_proto(s, projection.sleeve(str(s.id)).cash)
                        for s in base.values()
                    ],
                )
        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_or_create_account error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"account bootstrap failed: {e}") from e

    @staticmethod
    async def _backfill_account(
        db: AsyncSession, sleeves: SleeveService, tenant_id: UUID, credentials_id: UUID
    ) -> None:
        """Seed a newly created account from broker state (best-effort)."""
        from src.clients.alpaca import AlpacaBrokerPositions
        from src.services.onboarding_service import AccountOnboardingService

        try:
            onboarding = AccountOnboardingService(
                sleeves, SqlLedgerStore(db), AlpacaBrokerPositions(db)
            )
            await onboarding.onboard(tenant_id, credentials_id)
        except Exception:
            logger.exception(
                "broker backfill failed for credentials %s — account created unseeded; "
                "reconciliation will surface the gap until re-onboarded",
                credentials_id,
            )

    async def deposit_funds(
        self, request: ledger_pb2.DepositFundsRequest, ctx: AnyContext
    ) -> ledger_pb2.DepositFundsResponse:
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                fund = FundService(SqlSleeveRepository(db), SqlLedgerStore(db))
                view = await fund.deposit(
                    tenant_id=tenant_id, account_id=account_id, amount=_amount(request.amount)
                )
                await db.commit()
                return ledger_pb2.DepositFundsResponse(unallocated=_view_to_proto(view))
        except FundError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except Exception as e:
            logger.error("deposit_funds error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"deposit failed: {e}") from e

    async def withdraw_funds(
        self, request: ledger_pb2.WithdrawFundsRequest, ctx: AnyContext
    ) -> ledger_pb2.WithdrawFundsResponse:
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                fund = FundService(SqlSleeveRepository(db), SqlLedgerStore(db))
                view = await fund.withdraw(
                    tenant_id=tenant_id, account_id=account_id, amount=_amount(request.amount)
                )
                await db.commit()
                return ledger_pb2.WithdrawFundsResponse(unallocated=_view_to_proto(view))
        except FundError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except Exception as e:
            logger.error("withdraw_funds error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"withdraw failed: {e}") from e

    async def allocate_capital(
        self, request: ledger_pb2.AllocateCapitalRequest, ctx: AnyContext
    ) -> ledger_pb2.AllocateCapitalResponse:
        """Fund an existing sleeve, or open-and-fund a strategy sleeve.

        With an empty ``to_sleeve_id`` and a ``strategy_execution_id``, the
        strategy sleeve linked to that execution is opened (or reused) and
        funded in the same transaction (CONTRACTS.md §5).
        """
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        if not request.to_sleeve_id and not request.strategy_execution_id:
            raise ConnectError(
                Code.INVALID_ARGUMENT, "to_sleeve_id or strategy_execution_id required"
            )
        try:
            async with self._get_db() as db:
                repo = SqlSleeveRepository(db)
                to_sleeve_id = await self._resolve_allocation_target(repo, request, tenant_id)
                fund = FundService(repo, SqlLedgerStore(db))
                view = await fund.allocate(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    to_sleeve_id=to_sleeve_id,
                    amount=_amount(request.amount),
                )
                await db.commit()
                return ledger_pb2.AllocateCapitalResponse(sleeve=_view_to_proto(view))
        except FundError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except ConnectError:
            raise
        except Exception as e:
            logger.error("allocate_capital error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"allocate failed: {e}") from e

    @staticmethod
    async def _resolve_allocation_target(
        repo: SqlSleeveRepository, request: ledger_pb2.AllocateCapitalRequest, tenant_id: UUID
    ) -> UUID:
        """The sleeve to fund: the given one, or an opened strategy sleeve."""
        if request.to_sleeve_id:
            return UUID(request.to_sleeve_id)
        sleeves = SleeveService(repo)
        account = await repo.get_account(tenant_id, UUID(request.account_id))
        if account is None:
            raise ConnectError(Code.NOT_FOUND, f"account {request.account_id} not found")
        sleeve = await sleeves.get_or_create_strategy_sleeve(
            account,
            strategy_execution_id=UUID(request.strategy_execution_id),
            name=request.sleeve_name or f"Strategy {request.strategy_execution_id[:8]}",
            allocated_capital=_amount(request.amount),
        )
        return sleeve.id

    async def transfer_capital(
        self, request: ledger_pb2.TransferCapitalRequest, ctx: AnyContext
    ) -> ledger_pb2.TransferCapitalResponse:
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                fund = FundService(SqlSleeveRepository(db), SqlLedgerStore(db))
                from_view, to_view = await fund.transfer(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    from_sleeve_id=UUID(request.from_sleeve_id),
                    to_sleeve_id=UUID(request.to_sleeve_id),
                    amount=_amount(request.amount),
                )
                await db.commit()
                return ledger_pb2.TransferCapitalResponse(
                    from_sleeve=_view_to_proto(from_view), to_sleeve=_view_to_proto(to_view)
                )
        except FundError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except Exception as e:
            logger.error("transfer_capital error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"transfer failed: {e}") from e

    async def close_sleeve(
        self, request: ledger_pb2.CloseSleeveRequest, ctx: AnyContext
    ) -> ledger_pb2.CloseSleeveResponse:
        """Close a sleeve: re-home positions → Unmanaged, free cash → Unallocated.

        Idempotent. The strategy service calls this when an execution stops or
        its strategy is archived (the ledger owns sleeve lifecycle).
        """
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                lifecycle = SleeveLifecycleService(SqlSleeveRepository(db), SqlLedgerStore(db))
                result = await lifecycle.close_sleeve(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    sleeve_id=UUID(request.sleeve_id),
                    reason=request.reason or None,
                )
                projection = await LedgerProjector(db).project_account(tenant_id, account_id)
                await db.commit()
                sproj = projection.sleeve(str(result.sleeve.id))
                return ledger_pb2.CloseSleeveResponse(
                    sleeve=_sleeve_to_proto(
                        result.sleeve, sproj.cash, sproj.reserved, sproj.realized_pnl
                    ),
                    already_closed=result.already_closed,
                    rehomed_cash=_dec(result.rehomed_cash),
                    rehomed_positions=[
                        ledger_pb2.RehomedPosition(
                            symbol=p.symbol, qty=_dec(p.qty), cost_basis=_dec(p.cost_basis)
                        )
                        for p in result.rehomed_positions
                    ],
                )
        except SleeveCloseError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e)) from e
        except ConnectError:
            raise
        except Exception as e:
            logger.error("close_sleeve error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"close sleeve failed: {e}") from e

    async def list_sleeves(
        self, request: ledger_pb2.ListSleevesRequest, ctx: AnyContext
    ) -> ledger_pb2.ListSleevesResponse:
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                repo = SqlSleeveRepository(db)
                projection = await LedgerProjector(db).project_account(tenant_id, account_id)
                rows = await repo.list_sleeves(tenant_id, account_id)
                sleeves = [
                    _sleeve_to_proto(
                        s,
                        projection.sleeve(str(s.id)).cash,
                        projection.sleeve(str(s.id)).reserved,
                        projection.sleeve(str(s.id)).realized_pnl,
                    )
                    for s in rows
                ]
                return ledger_pb2.ListSleevesResponse(sleeves=sleeves)
        except Exception as e:
            logger.error("list_sleeves error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"list sleeves failed: {e}") from e

    async def get_sleeve(
        self, request: ledger_pb2.GetSleeveRequest, ctx: AnyContext
    ) -> ledger_pb2.GetSleeveResponse:
        tenant_id = UUID(request.context.tenant_id)
        try:
            async with self._get_db() as db:
                repo = SqlSleeveRepository(db)
                sleeve = await repo.get_sleeve(tenant_id, UUID(request.sleeve_id))
                if sleeve is None:
                    raise ConnectError(Code.NOT_FOUND, f"sleeve {request.sleeve_id} not found")
                projection = await LedgerProjector(db).project_account(tenant_id, sleeve.account_id)
                sleeve_proj = projection.sleeve(str(sleeve.id))
                lots = [
                    ledger_pb2.Lot(
                        tenant_id=str(sleeve.tenant_id),
                        sleeve_id=str(sleeve.id),
                        symbol=symbol,
                        side=(
                            ledger_pb2.LOT_SIDE_LONG if pos.qty >= 0 else ledger_pb2.LOT_SIDE_SHORT
                        ),
                        qty=_dec(pos.qty),
                        avg_price=_dec(pos.cost_basis / pos.qty if pos.qty else 0),
                        cost_basis=_dec(pos.cost_basis),
                        is_open=True,
                    )
                    for symbol, pos in sleeve_proj.positions.items()
                    if pos.qty != 0
                ]
                return ledger_pb2.GetSleeveResponse(
                    sleeve=_sleeve_to_proto(
                        sleeve, sleeve_proj.cash, sleeve_proj.reserved, sleeve_proj.realized_pnl
                    ),
                    lots=lots,
                )
        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_sleeve error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"get sleeve failed: {e}") from e

    async def get_holding_history(
        self, request: ledger_pb2.GetHoldingHistoryRequest, ctx: AnyContext
    ) -> ledger_pb2.GetHoldingHistoryResponse:
        tenant_id = UUID(request.context.tenant_id)
        account_id = UUID(request.account_id)
        try:
            async with self._get_db() as db:
                raw = cast(
                    list[HoldingHistoryEntry],
                    await LedgerProjector(db).holding_history(
                        tenant_id, account_id, request.symbol
                    ),
                )
                entries = [
                    ledger_pb2.HoldingHistoryEntry(
                        sleeve_id=e.sleeve_id,
                        side=e.side,
                        qty=_dec(e.qty),
                        price=_dec(e.price) if e.price is not None else _dec(0),
                        realized_pnl=_dec(e.realized_pnl)
                        if e.realized_pnl is not None
                        else _dec(0),
                    )
                    for e in raw
                ]
                return ledger_pb2.GetHoldingHistoryResponse(entries=entries)
        except Exception as e:
            logger.error("get_holding_history error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"holding history failed: {e}") from e
