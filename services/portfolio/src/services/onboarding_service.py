"""Account onboarding + broker backfill.

When an account is first provisioned we must seed the ledger from current broker
state so the invariant ``Σ sleeves == broker`` holds from day one: free cash →
Unallocated, pre-existing positions → Unmanaged (a strategy can't adopt them).

Composition only: account/sleeve creation goes through ``SleeveService``, the
seed events are planned by the pure ``backfill`` kernel, and each append is made
idempotent by a deterministic ``event_id`` derived from the account + dedup key —
so re-onboarding (or a crash-replay) never double-seeds.
"""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from llamatrade_db.models.ledger import Account, SleeveType

from src.ledger import backfill
from src.ports import BrokerSnapshotProvider, LedgerStore
from src.services.sleeve_service import SleeveService

logger = logging.getLogger(__name__)


def _backfill_event_id(account_id: UUID, dedup_key: str) -> UUID:
    """Deterministic, idempotent event id for a backfill seed event."""
    digest = hashlib.sha256(f"{account_id}:{dedup_key}".encode()).digest()
    return UUID(bytes=digest[:16])


class AccountOnboardingService:
    """Provisions a ledger account and seeds it from current broker state."""

    def __init__(
        self,
        sleeves: SleeveService,
        store: LedgerStore,
        broker: BrokerSnapshotProvider,
    ) -> None:
        self._sleeves = sleeves
        self._store = store
        self._broker = broker

    async def onboard(self, tenant_id: UUID, credentials_id: UUID) -> Account:
        """Create the account + base sleeves and backfill broker cash/positions.

        Idempotent: re-running returns the same account and appends no duplicate
        seed events (the writer dedups on the deterministic ``event_id``)."""
        account = await self._sleeves.get_or_create_account(tenant_id, credentials_id)
        base = await self._sleeves.ensure_base_sleeves(account)
        unallocated = base[SleeveType.UNALLOCATED]
        unmanaged = base[SleeveType.UNMANAGED]

        snapshot = await self._broker.snapshot(tenant_id, account)
        planned = backfill.plan_backfill(
            broker_cash=snapshot.cash,
            broker_positions=[
                backfill.BrokerPosition(symbol=h.symbol, qty=h.qty, avg_price=h.avg_price)
                for h in snapshot.holdings
            ],
            unallocated_sleeve_id=unallocated.id,
            unmanaged_sleeve_id=unmanaged.id,
        )
        for event in planned:
            await self._store.append(
                tenant_id=tenant_id,
                account_id=account.id,
                event_type=event.event_type,
                data=dict(event.data),
                sleeve_id=event.sleeve_id,
                event_id=_backfill_event_id(account.id, event.dedup_key),
            )
        logger.info("onboarded account %s: seeded %d backfill event(s)", account.id, len(planned))
        return account
