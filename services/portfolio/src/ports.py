"""Injectable I/O boundaries (ports) for the portfolio service.

Production adapters wrap gRPC/DB; tests supply in-memory fakes so the service
logic suite runs with **no third-party dependency** (no network, no live market
data, no sibling services). Any object that structurally matches a Protocol
satisfies it — the concrete ``clients.market_data.MarketDataClient`` already
implements ``PriceProvider``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from llamatrade_db.models.ledger import Account, LedgerEventType, Sleeve, SleeveType

    from src.ledger.projection import AccountProjection


@runtime_checkable
class PriceProvider(Protocol):
    """Source of current and historical prices (market-data adapter)."""

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        """Latest price per symbol."""
        ...

    async def get_daily_closes(
        self, symbol: str, start: datetime, end: datetime
    ) -> dict[date, float]:
        """Daily close prices keyed by date over a window."""
        ...


class SleeveRepository(Protocol):
    """Persistence boundary for ledger Account/Sleeve rows (metadata only).

    Cash/positions/P&L are projections of the event log, not stored here; this
    port covers the durable identity/metadata rows. A SQLAlchemy adapter backs
    it in production; tests use an in-memory fake.
    """

    async def get_account_by_credentials(
        self, tenant_id: UUID, credentials_id: UUID
    ) -> Account | None: ...

    async def get_account(self, tenant_id: UUID, account_id: UUID) -> Account | None: ...

    async def add_account(self, account: Account) -> None: ...

    async def get_sleeve(self, tenant_id: UUID, sleeve_id: UUID) -> Sleeve | None: ...

    async def get_sleeve_by_type(
        self, tenant_id: UUID, account_id: UUID, sleeve_type: SleeveType
    ) -> Sleeve | None: ...

    async def get_strategy_sleeve(
        self, tenant_id: UUID, account_id: UUID, strategy_execution_id: UUID
    ) -> Sleeve | None: ...

    async def list_sleeves(self, tenant_id: UUID, account_id: UUID) -> list[Sleeve]: ...

    async def set_sleeve_status(self, sleeve: Sleeve, status: str) -> None: ...

    async def add_sleeve(self, sleeve: Sleeve) -> None: ...


class LedgerStore(Protocol):
    """Append events to (and project from) the ledger event log.

    The two always go together for a transactional fund op (append → reproject),
    so they share one port. The SQL adapter wraps ``LedgerWriter`` +
    ``LedgerProjector``; tests use an in-memory log folded by the real kernel.
    """

    async def append(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        event_type: LedgerEventType,
        data: dict[str, Any],
        sleeve_id: UUID | None = None,
        event_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ) -> Any: ...

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection: ...


class BrokerUnavailableError(Exception):
    """The broker truth couldn't be read (missing credentials / transport fault).

    Distinct from "the broker holds nothing": reconciliation MUST NOT treat an
    unreadable account as an empty one, or every ledger holding would look like a
    ``MISSING_AT_BROKER`` drift and freeze every sleeve. Callers skip the account
    for this pass and retry next cycle.
    """


class BrokerPositions(Protocol):
    """Read aggregate broker truth for reconciliation (one qty per symbol).

    Production adapter resolves the account's Alpaca credentials and calls the
    broker via ``llamatrade_alpaca``; tests supply a static in-memory map.
    Raises :class:`BrokerUnavailableError` when the broker can't be read (so an
    unreadable account is never mistaken for an empty one).
    """

    async def positions(self, tenant_id: UUID, account: Account) -> dict[str, Decimal]:
        """Aggregate signed quantity per symbol held at the broker."""
        ...


@dataclass(frozen=True)
class BrokerHolding:
    """A pre-existing broker position to seed during onboarding."""

    symbol: str
    qty: Decimal
    avg_price: Decimal


@dataclass(frozen=True)
class BrokerSnapshot:
    """Point-in-time broker truth used to backfill a newly onboarded account."""

    cash: Decimal
    holdings: list[BrokerHolding]


class BrokerSnapshotProvider(Protocol):
    """Read full broker state (cash + holdings) for account backfill."""

    async def snapshot(self, tenant_id: UUID, account: Account) -> BrokerSnapshot:
        """Current broker cash and holdings for the account."""
        ...
