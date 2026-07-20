"""Corporate-action driver: apply a broker corporate action to the ledger.

Triggered by an operator (or a future automated feed) via the LedgerService
``ApplyCorporateAction`` RPC. A split / ticker-rename / dividend is fanned across
**every sleeve** holding the symbol (via the pure ``corporate`` planners) so
per-sleeve provenance and cost basis stay correct — and the drift policy no
longer freezes those sleeves once the action is applied. Idempotent: each planned
event's dedup key maps to a deterministic ledger event id, so re-submitting the
same action never double-applies.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

from src.ledger import corporate
from src.ports import LedgerStore


def _event_id(dedup_key: str) -> UUID:
    """Deterministic ledger event id from a planner dedup key (idempotency)."""
    return UUID(bytes=hashlib.sha256(dedup_key.encode()).digest()[:16])


class CorporateActionService:
    """Applies corporate actions to the ledger (fan-out across holding sleeves)."""

    def __init__(self, store: LedgerStore) -> None:
        self._store = store

    async def apply_split(
        self, *, tenant_id: UUID, account_id: UUID, symbol: str, ratio: Decimal
    ) -> int:
        proj = await self._store.project_account(tenant_id, account_id)
        holders = {
            UUID(sid): s.positions[symbol].qty
            for sid, s in proj.sleeves.items()
            if symbol in s.positions and s.positions[symbol].qty != corporate.ZERO
        }
        events = corporate.plan_split(symbol=symbol, ratio=ratio, holders=holders)
        return await self._append_all(tenant_id, account_id, events)

    async def apply_symbol_change(
        self, *, tenant_id: UUID, account_id: UUID, old_symbol: str, new_symbol: str
    ) -> int:
        proj = await self._store.project_account(tenant_id, account_id)
        holders = {
            UUID(sid): (s.positions[old_symbol].qty, s.positions[old_symbol].cost_basis)
            for sid, s in proj.sleeves.items()
            if old_symbol in s.positions and s.positions[old_symbol].qty != corporate.ZERO
        }
        events = corporate.plan_symbol_change(
            old_symbol=old_symbol, new_symbol=new_symbol, holders=holders
        )
        return await self._append_all(tenant_id, account_id, events)

    async def apply_dividend(
        self, *, tenant_id: UUID, account_id: UUID, symbol: str, total_amount: Decimal, pay_id: str
    ) -> int:
        proj = await self._store.project_account(tenant_id, account_id)
        holders = {
            UUID(sid): s.positions[symbol].qty
            for sid, s in proj.sleeves.items()
            if symbol in s.positions and s.positions[symbol].qty > corporate.ZERO
        }
        events = corporate.split_dividend(
            symbol=symbol, total_amount=total_amount, holders=holders, pay_id=pay_id
        )
        return await self._append_all(tenant_id, account_id, events)

    async def _append_all(
        self, tenant_id: UUID, account_id: UUID, events: list[corporate.PlannedCorporateEvent]
    ) -> int:
        for ev in events:
            await self._store.append(
                tenant_id=tenant_id,
                account_id=account_id,
                event_type=ev.event_type,
                data=ev.data,
                sleeve_id=ev.sleeve_id,
                event_id=_event_id(ev.dedup_key),
            )
        return len(events)
