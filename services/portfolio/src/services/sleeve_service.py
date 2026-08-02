"""Sleeve lifecycle & account bootstrap.

Lazily creates one ledger ``Account`` per broker account, the three singleton
base sleeves (Unallocated / Manual / Unmanaged), and a ``strategy`` sleeve per
funded ``StrategyExecution``. Pure metadata management over the
``SleeveRepository`` port — cash/positions are projections of the event log and
are *not* set here (funding happens via ``FundService``).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType

from src.ports import SleeveRepository

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Singleton base sleeves every account has, with their display names.
_BASE_SLEEVES: dict[SleeveType, str] = {
    SleeveType.UNALLOCATED: "Unallocated",
    SleeveType.MANUAL: "Manual",
    SleeveType.UNMANAGED: "Unmanaged",
}


class SleeveService:
    """Bootstraps accounts and sleeves (identity/metadata rows)."""

    def __init__(self, repo: SleeveRepository) -> None:
        self._repo = repo

    async def get_or_create_account(
        self, tenant_id: UUID, credentials_id: UUID, broker_account_id: str | None = None
    ) -> Account:
        """The account for a credential set; see :meth:`resolve_account`."""
        account, _created = await self.resolve_account(tenant_id, credentials_id, broker_account_id)
        return account

    async def resolve_account(
        self, tenant_id: UUID, credentials_id: UUID, broker_account_id: str | None = None
    ) -> tuple[Account, bool]:
        """One ``Account`` per (tenant, broker account); the flag is True when created.

        The broker account id is the durable identity: a credential set that was
        deleted and re-added resolves back to the account that already holds the
        broker's positions, and that account's ``credentials_id`` is re-pointed
        at the new row. Only a broker account this tenant has never booked gets a
        new ledger account. Callers that cannot read the broker (or predate the
        column) pass ``None`` and fall back to credential identity.

        The flag tells a caller whether the book is new; seeding an account that
        already has history would import its current positions a second time.
        """
        account = await self._repo.get_account_by_credentials(tenant_id, credentials_id)
        if account is not None:
            if broker_account_id is not None:
                await self._adopt_broker_id(account, broker_account_id)
            return account, False

        if broker_account_id is not None:
            relinked = await self._repo.get_account_by_broker_id(tenant_id, broker_account_id)
            if relinked is not None:
                logger.info(
                    "re-linking ledger account %s from credentials %s to %s (broker account %s)",
                    relinked.id,
                    relinked.credentials_id,
                    credentials_id,
                    broker_account_id,
                )
                await self._repo.set_account_credentials(relinked, credentials_id)
                return relinked, False

        account = Account(
            tenant_id=tenant_id,
            credentials_id=credentials_id,
            alpaca_account_id=broker_account_id,
        )
        await self._repo.add_account(account)
        return account, True

    async def _adopt_broker_id(self, account: Account, broker_account_id: str) -> None:
        """Record the broker identity on an account that resolved by credentials.

        Backfills the id the first time a broker snapshot supplies it. Two states
        are reported and never resolved here: another account in the tenant
        already claims this broker account (merging two event logs is an operator
        decision), or these credentials now point at a different broker account
        than the book was built from.
        """
        if account.alpaca_account_id == broker_account_id:
            return
        if account.alpaca_account_id is not None:
            logger.error(
                "ledger account %s is booked against broker account %s but its credentials "
                "%s now report %s; leaving the account untouched",
                account.id,
                account.alpaca_account_id,
                account.credentials_id,
                broker_account_id,
            )
            return
        other = await self._repo.get_account_by_broker_id(account.tenant_id, broker_account_id)
        if other is not None:
            logger.error(
                "duplicate ledger accounts for broker account %s in tenant %s: %s and %s; "
                "resolve manually — positions are double-counted until then",
                broker_account_id,
                account.tenant_id,
                other.id,
                account.id,
            )
            return
        await self._repo.set_account_broker_id(account, broker_account_id)

    async def ensure_base_sleeves(self, account: Account) -> dict[SleeveType, Sleeve]:
        """Ensure the singleton Unallocated/Manual/Unmanaged sleeves exist."""
        sleeves: dict[SleeveType, Sleeve] = {}
        for sleeve_type, name in _BASE_SLEEVES.items():
            sleeve = await self._repo.get_sleeve_by_type(account.tenant_id, account.id, sleeve_type)
            if sleeve is None:
                sleeve = self._new_sleeve(account, sleeve_type, name)
                await self._repo.add_sleeve(sleeve)
            sleeves[sleeve_type] = sleeve
        return sleeves

    async def unallocated_sleeve(self, account: Account) -> Sleeve:
        """The account's free-cash pool (created if missing)."""
        return (await self.ensure_base_sleeves(account))[SleeveType.UNALLOCATED]

    async def get_or_create_strategy_sleeve(
        self,
        account: Account,
        strategy_execution_id: UUID,
        name: str,
        allocated_capital: Decimal = ZERO,
    ) -> Sleeve:
        """Get (or open) the ``strategy`` sleeve for an execution.

        The sleeve's *cash* is funded separately via ``FundService.allocate`` —
        ``allocated_capital`` here is only the budget anchor stored on the row.
        """
        sleeve = await self._repo.get_strategy_sleeve(
            account.tenant_id, account.id, strategy_execution_id
        )
        if sleeve is None:
            sleeve = self._new_sleeve(
                account,
                SleeveType.STRATEGY,
                name,
                strategy_execution_id=strategy_execution_id,
                allocated_capital=allocated_capital,
            )
            await self._repo.add_sleeve(sleeve)
        return sleeve

    def _new_sleeve(
        self,
        account: Account,
        sleeve_type: SleeveType,
        name: str,
        *,
        strategy_execution_id: UUID | None = None,
        allocated_capital: Decimal = ZERO,
    ) -> Sleeve:
        return Sleeve(
            tenant_id=account.tenant_id,
            account_id=account.id,
            type=sleeve_type.value,
            status=SleeveStatus.ACTIVE.value,
            name=name,
            strategy_execution_id=strategy_execution_id,
            allocated_capital=allocated_capital,
        )
