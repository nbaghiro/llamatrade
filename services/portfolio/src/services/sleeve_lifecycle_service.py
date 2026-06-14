"""Transactional sleeve lifecycle transitions, backed by the ledger event log.

Closing a strategy sleeve re-homes its open positions to the account's
Unmanaged sleeve and its free cash to Unallocated, appends a ``SLEEVE_CLOSED``
event (the book-of-record record of the close), and flips the sleeve's
materialized status to CLOSED. The strategy service owns sleeve lifecycle
(it opens/funds the sleeve via ``FundService``; it closes it here).

The close is:

- **idempotent** — a re-home runs at most once. A second call short-circuits on
  the CLOSED status, and the deterministic ``event_id`` makes the append a no-op
  even if status persistence was interrupted mid-transaction;
- **conservation-preserving** — re-homing moves value between sleeves (balanced
  postings), so account-level cash and per-symbol quantity are unchanged;
- **clean** — it refuses while cash is reserved for in-flight orders, so a
  stopped strategy never closes with money committed to an open order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType, Sleeve, SleeveStatus, SleeveType

from src.ledger.lifecycle import (
    RehomedPosition,
    SleeveCloseError,
    close_event_id,
    plan_sleeve_close,
)
from src.ports import LedgerStore, SleeveRepository

ZERO = Decimal("0")

# The re-home targets themselves: base singleton sleeves must never be closed.
_UNCLOSEABLE_TYPES = {SleeveType.UNALLOCATED.value, SleeveType.UNMANAGED.value}


@dataclass(frozen=True)
class CloseResult:
    """Outcome of a close: the sleeve and what (if anything) was re-homed."""

    sleeve: Sleeve
    rehomed_positions: tuple[RehomedPosition, ...]
    rehomed_cash: Decimal
    already_closed: bool


class SleeveLifecycleService:
    """Close (re-home + retire) sleeves against the ledger."""

    def __init__(self, repo: SleeveRepository, store: LedgerStore) -> None:
        self._repo = repo
        self._store = store

    async def close_sleeve(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        sleeve_id: UUID,
        reason: str | None = None,
    ) -> CloseResult:
        """Re-home a sleeve's holdings and retire it. See module docstring.

        Raises :class:`SleeveCloseError` if the sleeve is missing, is a base
        sleeve, still has reserved cash (in-flight orders), or the account is
        missing its base sleeves.
        """
        sleeve = await self._repo.get_sleeve(tenant_id, sleeve_id)
        if sleeve is None or sleeve.account_id != account_id:
            raise SleeveCloseError(f"sleeve {sleeve_id} not found in account {account_id}")
        if sleeve.type in _UNCLOSEABLE_TYPES:
            raise SleeveCloseError(f"cannot close a base {sleeve.type} sleeve")

        # Idempotent: the re-home already happened on a prior call.
        if sleeve.status == SleeveStatus.CLOSED.value:
            return CloseResult(sleeve, (), ZERO, already_closed=True)

        proj = await self._store.project_account(tenant_id, account_id)
        s = proj.sleeve(str(sleeve_id))

        # A clean close needs no money committed to open orders. With the
        # decoupled stop orchestration the runner halts first, so reservations
        # settle to zero; if one is still open, refuse so the caller retries
        # once it reaches a terminal state.
        if s.reserved != ZERO:
            raise SleeveCloseError(
                f"sleeve {sleeve_id} has {s.reserved} reserved for in-flight orders; "
                "retry after they reach a terminal state"
            )

        unmanaged = await self._repo.get_sleeve_by_type(tenant_id, account_id, SleeveType.UNMANAGED)
        unallocated = await self._repo.get_sleeve_by_type(
            tenant_id, account_id, SleeveType.UNALLOCATED
        )
        if unmanaged is None or unallocated is None:
            raise SleeveCloseError(
                f"account {account_id} is missing base sleeves; bootstrap it first"
            )

        positions = [
            RehomedPosition(symbol=symbol, qty=pos.qty, cost_basis=pos.cost_basis)
            for symbol, pos in s.positions.items()
            if pos.qty != ZERO
        ]
        # reserved == 0 here, so the full balance is free cash.
        plan = plan_sleeve_close(
            from_sleeve_id=sleeve_id,
            positions=positions,
            cash=s.cash,
            unmanaged_sleeve_id=unmanaged.id,
            unallocated_sleeve_id=unallocated.id,
            reason=reason,
        )
        await self._store.append(
            tenant_id=tenant_id,
            account_id=account_id,
            event_type=LedgerEventType.SLEEVE_CLOSED,
            data=plan.event_data,
            sleeve_id=sleeve_id,
            event_id=close_event_id(sleeve_id),
        )
        await self._repo.set_sleeve_status(sleeve, SleeveStatus.CLOSED.value)
        return CloseResult(
            sleeve=sleeve,
            rehomed_positions=plan.positions,
            rehomed_cash=plan.cash,
            already_closed=False,
        )
