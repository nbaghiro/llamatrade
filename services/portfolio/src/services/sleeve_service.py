"""Sleeve lifecycle & account bootstrap.

Lazily creates one ledger ``Account`` per broker credential set, the three
singleton base sleeves (Unallocated / Manual / Unmanaged), and a ``strategy``
sleeve per funded ``StrategyExecution``. Pure metadata management over the
``SleeveRepository`` port — cash/positions are projections of the event log and
are *not* set here (funding happens via ``FundService``).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType

from src.ports import SleeveRepository

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

    async def get_or_create_account(self, tenant_id: UUID, credentials_id: UUID) -> Account:
        """One ``Account`` per (tenant, broker credential set), created on first use."""
        account = await self._repo.get_account_by_credentials(tenant_id, credentials_id)
        if account is None:
            account = Account(tenant_id=tenant_id, credentials_id=credentials_id)
            await self._repo.add_account(account)
        return account

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
