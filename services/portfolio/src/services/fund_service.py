"""Transactional fund disbursement.

Wraps the pure planners in ``src/ledger/funds.py`` with the ledger store: read
the current projection for free cash, plan the balanced events, append them, and
reproject. Free cash always comes from the projection (the event log is the
source of truth) — never from a mutable balance column.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from llamatrade_db.models.ledger import Sleeve, SleeveType
from llamatrade_telemetry import metrics

from src.ledger import funds
from src.ledger.projection import AccountProjection
from src.ports import LedgerStore, SleeveRepository

ZERO = Decimal("0")


@dataclass(frozen=True)
class SleeveView:
    """A sleeve row plus its projected free cash (book-of-record balance)."""

    sleeve: Sleeve
    cash: Decimal


class FundService:
    """Allocate / transfer / deposit / withdraw against the ledger."""

    def __init__(self, repo: SleeveRepository, store: LedgerStore) -> None:
        self._repo = repo
        self._store = store

    async def deposit(self, *, tenant_id: UUID, account_id: UUID, amount: Decimal) -> SleeveView:
        """Deposit external cash into the Unallocated sleeve."""
        unalloc = await self._require_unallocated(tenant_id, account_id)
        await self._append_all(
            tenant_id,
            account_id,
            funds.plan_deposit(unallocated_sleeve_id=unalloc.id, amount=amount),
        )
        proj = await self._store.project_account(tenant_id, account_id)
        self._record_capital(proj, unalloc.id)
        return SleeveView(unalloc, proj.sleeve(str(unalloc.id)).cash)

    async def withdraw(self, *, tenant_id: UUID, account_id: UUID, amount: Decimal) -> SleeveView:
        """Withdraw external cash from the Unallocated sleeve's free cash."""
        unalloc = await self._require_unallocated(tenant_id, account_id)
        free = await self._free_cash(tenant_id, account_id, unalloc.id)
        await self._append_all(
            tenant_id,
            account_id,
            funds.plan_withdraw(sleeve_id=unalloc.id, amount=amount, free_cash=free),
        )
        proj = await self._store.project_account(tenant_id, account_id)
        self._record_capital(proj, unalloc.id)
        return SleeveView(unalloc, proj.sleeve(str(unalloc.id)).cash)

    async def allocate(
        self, *, tenant_id: UUID, account_id: UUID, to_sleeve_id: UUID, amount: Decimal
    ) -> SleeveView:
        """Allocate cash from Unallocated into an existing sleeve."""
        unalloc = await self._require_unallocated(tenant_id, account_id)
        to_sleeve = await self._require_sleeve(tenant_id, account_id, to_sleeve_id)
        free = await self._free_cash(tenant_id, account_id, unalloc.id)
        if free < amount:
            # Under-capitalized: the planner will reject this with a FundError; the
            # gauge records the attempt before the exception propagates.
            metrics.ledger.capital_insufficient()
        await self._append_all(
            tenant_id,
            account_id,
            funds.plan_allocate(
                from_sleeve_id=unalloc.id,
                to_sleeve_id=to_sleeve_id,
                amount=amount,
                from_free_cash=free,
            ),
        )
        proj = await self._store.project_account(tenant_id, account_id)
        self._record_capital(proj, unalloc.id)
        return SleeveView(to_sleeve, proj.sleeve(str(to_sleeve_id)).cash)

    async def transfer(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        from_sleeve_id: UUID,
        to_sleeve_id: UUID,
        amount: Decimal,
    ) -> tuple[SleeveView, SleeveView]:
        """Move cash sleeve→sleeve. Only liquid transfers are supported: raising
        cash by selling the source sleeve's lots needs the trading arm to execute
        the sells, so illiquid transfers are rejected."""
        from_sleeve = await self._require_sleeve(tenant_id, account_id, from_sleeve_id)
        to_sleeve = await self._require_sleeve(tenant_id, account_id, to_sleeve_id)
        free = await self._free_cash(tenant_id, account_id, from_sleeve_id)
        if free < amount:
            raise funds.FundError(
                "transfer requires raising cash by selling positions, which is not "
                "yet supported; transfer only liquid (free-cash) amounts"
            )
        plan = funds.plan_transfer(
            from_sleeve_id=from_sleeve_id,
            to_sleeve_id=to_sleeve_id,
            amount=amount,
            from_free_cash=free,
        )
        await self._store.append(
            tenant_id=tenant_id,
            account_id=account_id,
            event_type=plan.transfer.event_type,
            data=dict(plan.transfer.data),
        )
        proj = await self._store.project_account(tenant_id, account_id)
        # Best-effort capital telemetry: a transfer doesn't require resolving the
        # Unallocated sleeve, so never let a missing one turn a good transfer into
        # a failure — just skip the gauge update.
        unalloc = await self._repo.get_sleeve_by_type(tenant_id, account_id, SleeveType.UNALLOCATED)
        if unalloc is not None:
            self._record_capital(proj, unalloc.id)
        return (
            SleeveView(from_sleeve, proj.sleeve(str(from_sleeve_id)).cash),
            SleeveView(to_sleeve, proj.sleeve(str(to_sleeve_id)).cash),
        )

    # ----------------------------------------------------------------- helpers

    async def _require_unallocated(self, tenant_id: UUID, account_id: UUID) -> Sleeve:
        sleeve = await self._repo.get_sleeve_by_type(tenant_id, account_id, SleeveType.UNALLOCATED)
        if sleeve is None:
            raise funds.FundError("account has no Unallocated sleeve; bootstrap the account first")
        return sleeve

    async def _require_sleeve(self, tenant_id: UUID, account_id: UUID, sleeve_id: UUID) -> Sleeve:
        sleeve = await self._repo.get_sleeve(tenant_id, sleeve_id)
        if sleeve is None or sleeve.account_id != account_id:
            raise funds.FundError(f"sleeve {sleeve_id} not found in account {account_id}")
        return sleeve

    async def _free_cash(self, tenant_id: UUID, account_id: UUID, sleeve_id: UUID) -> Decimal:
        # Free cash = balance − reserved (cash earmarked for open buy orders).
        # Affordability checks (withdraw/allocate/transfer) must never spend
        # reserved funds, or a concurrent open order could overdraw the account.
        proj = await self._store.project_account(tenant_id, account_id)
        s = proj.sleeve(str(sleeve_id))
        return s.cash - s.reserved

    async def _append_all(
        self, tenant_id: UUID, account_id: UUID, events: list[funds.PlannedFundEvent]
    ) -> None:
        for ev in events:
            await self._store.append(
                tenant_id=tenant_id,
                account_id=account_id,
                event_type=ev.event_type,
                data=dict(ev.data),
            )

    def _record_capital(self, projection: AccountProjection, unallocated_sleeve_id: UUID) -> None:
        """Publish the account's allocated/unallocated capital split as gauges.

        Unallocated capital is the cash idle in the Unallocated sleeve; allocated
        capital is the cash put to work in every other sleeve (strategy / manual /
        unmanaged). Reservations are not netted out — these are book balances, not
        free cash.
        """
        unallocated_key = str(unallocated_sleeve_id)
        unallocated = projection.sleeve(unallocated_key).cash
        allocated = sum(
            (s.cash for key, s in projection.sleeves.items() if key != unallocated_key),
            ZERO,
        )
        metrics.ledger.capital_allocated_dollars.set(float(allocated))
        metrics.ledger.capital_unallocated_dollars.set(float(unallocated))
