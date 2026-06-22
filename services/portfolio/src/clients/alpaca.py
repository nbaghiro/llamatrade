"""Broker-truth adapter for reconciliation (read-only).

Resolves an account's stored Alpaca credentials and reads its aggregate
positions via ``llamatrade_alpaca`` — never by talking to Alpaca directly. The
reconciliation task compares this broker truth against the ledger projection.

The pure ``positions_to_qty_map`` translation is unit-tested; the credential
resolution + HTTP call is the thin IO shell (exercised by the integration suite).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_alpaca import TradingClient
from llamatrade_common.utils import decrypt_value
from llamatrade_db.models.auth import AlpacaCredentials

from src.ports import BrokerHolding, BrokerSnapshot, BrokerUnavailableError

if TYPE_CHECKING:
    from llamatrade_alpaca.models.trading import Position
    from llamatrade_db.models.ledger import Account

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _safe_decimal(value: object) -> Decimal | None:
    """Parse a broker-supplied numeric, or None if it's malformed."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def positions_to_qty_map(positions: list[Position]) -> dict[str, Decimal]:
    """Reduce broker positions to a signed aggregate quantity per symbol.

    Alpaca already nets to one position per symbol, but we aggregate defensively
    so duplicates (or a future per-account split) collapse correctly. A position
    with an unparseable quantity is skipped (logged) rather than failing the whole
    reconciliation pass for the account.
    """
    qty_map: dict[str, Decimal] = {}
    for pos in positions:
        qty = _safe_decimal(pos.qty)
        if qty is None:
            logger.warning("skipping broker position with unparseable qty: %s=%r", pos.symbol, pos.qty)
            continue
        qty_map[pos.symbol] = qty_map.get(pos.symbol, _ZERO) + qty
    return qty_map


def positions_to_holdings(positions: list[Position]) -> list[BrokerHolding]:
    """Translate broker positions into backfill holdings (symbol/qty/avg_price).

    A position with an unparseable qty or average price is skipped (logged), so a
    single malformed broker row can't abort onboarding/backfill.
    """
    holdings: list[BrokerHolding] = []
    for pos in positions:
        qty = _safe_decimal(pos.qty)
        avg_price = _safe_decimal(pos.avg_entry_price)
        if qty is None or avg_price is None:
            logger.warning(
                "skipping malformed broker position: %s qty=%r avg=%r",
                pos.symbol,
                pos.qty,
                pos.avg_entry_price,
            )
            continue
        if qty != _ZERO:
            holdings.append(BrokerHolding(symbol=pos.symbol, qty=qty, avg_price=avg_price))
    return holdings


class AlpacaBrokerPositions:
    """Broker-truth adapter (``BrokerPositions`` + ``BrokerSnapshotProvider``).

    Backed by the account's stored Alpaca keys; resolves credentials per account
    so reconciliation and onboarding honor the BYO-keys model and tenant isolation.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def positions(self, tenant_id: UUID, account: Account) -> dict[str, Decimal]:
        client = await self._client_for(tenant_id, account)
        if client is None:
            # No usable credentials → broker truth is UNKNOWN, not empty. Raising
            # (vs. returning {}) keeps reconciliation from reading every ledger
            # holding as MISSING_AT_BROKER and freezing every sleeve.
            raise BrokerUnavailableError(
                f"no active Alpaca credentials for account {account.id}"
            )
        try:
            broker_positions = await client.get_positions()
        finally:
            await client.close()
        return positions_to_qty_map(broker_positions)

    async def snapshot(self, tenant_id: UUID, account: Account) -> BrokerSnapshot:
        client = await self._client_for(tenant_id, account)
        if client is None:
            return BrokerSnapshot(cash=Decimal("0"), holdings=[])
        try:
            broker_account = await client.get_account()
            broker_positions = await client.get_positions()
        finally:
            await client.close()
        return BrokerSnapshot(
            cash=Decimal(str(broker_account.cash)),
            holdings=positions_to_holdings(broker_positions),
        )

    async def _client_for(self, tenant_id: UUID, account: Account) -> TradingClient | None:
        creds = await self._resolve_credentials(tenant_id, account.credentials_id)
        if creds is None:
            logger.warning(
                "no active Alpaca credentials for account %s (credentials_id=%s); "
                "skipping broker read",
                account.id,
                account.credentials_id,
            )
            return None
        return TradingClient(
            api_key=decrypt_value(creds.api_key_encrypted),
            api_secret=decrypt_value(creds.api_secret_encrypted),
            paper=creds.is_paper,
        )

    async def _resolve_credentials(
        self, tenant_id: UUID, credentials_id: UUID
    ) -> AlpacaCredentials | None:
        return await self._db.scalar(
            select(AlpacaCredentials)
            .where(AlpacaCredentials.id == credentials_id)
            .where(AlpacaCredentials.tenant_id == tenant_id)  # tenant isolation
            .where(AlpacaCredentials.is_active.is_(True))
        )
