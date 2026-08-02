"""Persisted incremental-projection checkpoints (second-level checkpoint cache).

``LedgerProjector.project_account_incremental`` keeps a process-local LRU of
fold checkpoints; this store persists them so a restarted process seeds from
the last committed checkpoint and folds only the delta, instead of replaying
each account's full event history. Rows are derived state — deleting one only
costs a re-fold.

The serialized ``state`` is a deterministic JSON document: Decimals as strings
(exact scale-preserving round-trip), sets as sorted lists, mapping keys sorted.
It also carries the per-(sleeve, symbol) FIFO lot book (``lots``), so a resumed
fill-ingestion resolves a sell's cost basis from the checkpoint + delta rather
than folding the account's full history. :func:`decode_state` / :func:`decode_lots`
are strict — any unexpected shape, type, non-finite amount, or version raises
:class:`CheckpointStateError`, and :func:`load` treats the row as unreadable
(full re-fold with a warning) rather than folding a delta onto a wrong seed.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import ProjectionCheckpoint

from src.ledger.projection import (
    AccountLotBook,
    AccountProjection,
    Lot,
    PositionState,
    ReservationState,
    SleeveProjection,
)

logger = logging.getLogger(__name__)

# Bump when the fold-state shape changes; older persisted rows then re-fold.
STATE_VERSION = 2


class CheckpointStateError(ValueError):
    """A persisted checkpoint state has an unexpected shape, type, or version."""


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CheckpointStateError(f"{field}: expected object, got {type(value).__name__}")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CheckpointStateError(f"{field}: expected string, got {type(value).__name__}")
    return value


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CheckpointStateError(f"{field}: expected integer, got {type(value).__name__}")
    return value


def _decimal(value: object, field: str) -> Decimal:
    # Strings only: a float here means the state was built lossily — refuse it.
    if not isinstance(value, str):
        raise CheckpointStateError(f"{field}: expected decimal string, got {type(value).__name__}")
    try:
        parsed = Decimal(value)
    except ArithmeticError as exc:
        raise CheckpointStateError(f"{field}: invalid decimal {value!r}") from exc
    if not parsed.is_finite():
        raise CheckpointStateError(f"{field}: non-finite decimal {value!r}")
    return parsed


def encode_state(projection: AccountProjection, reservations: ReservationState) -> dict[str, Any]:
    """Serialize the full fold state to a deterministic JSON-compatible dict."""
    return {
        "v": STATE_VERSION,
        "projection": {
            "poison_events": projection.poison_events,
            "sleeves": {
                sleeve_id: {
                    "cash": str(sleeve.cash),
                    "realized_pnl": str(sleeve.realized_pnl),
                    "reserved": str(sleeve.reserved),
                    "positions": {
                        symbol: {"qty": str(pos.qty), "cost_basis": str(pos.cost_basis)}
                        for symbol, pos in sorted(sleeve.positions.items())
                    },
                }
                for sleeve_id, sleeve in sorted(projection.sleeves.items())
            },
        },
        "reservations": {
            "pending": {
                coid: {"sleeve_id": sleeve_id, "amount": str(amount)}
                for coid, (sleeve_id, amount) in sorted(reservations.pending.items())
            },
            "terminal": sorted(reservations.terminal),
        },
    }


def decode_state(raw: object) -> tuple[AccountProjection, ReservationState]:
    """Strictly deserialize :func:`encode_state` output (exact round-trip)."""
    root = _mapping(raw, "state")
    if _integer(root.get("v"), "v") != STATE_VERSION:
        raise CheckpointStateError(f"unsupported checkpoint state version {root.get('v')!r}")

    proj_raw = _mapping(root.get("projection"), "projection")
    sleeves: dict[str, SleeveProjection] = {}
    for sleeve_id, sleeve_value in _mapping(proj_raw.get("sleeves"), "sleeves").items():
        prefix = f"sleeves[{sleeve_id}]"
        sleeve_raw = _mapping(sleeve_value, prefix)
        positions: dict[str, PositionState] = {}
        for symbol, pos_value in _mapping(
            sleeve_raw.get("positions"), f"{prefix}.positions"
        ).items():
            pos_raw = _mapping(pos_value, f"{prefix}.positions[{symbol}]")
            positions[str(symbol)] = PositionState(
                qty=_decimal(pos_raw.get("qty"), f"{prefix}.positions[{symbol}].qty"),
                cost_basis=_decimal(
                    pos_raw.get("cost_basis"), f"{prefix}.positions[{symbol}].cost_basis"
                ),
            )
        sleeves[str(sleeve_id)] = SleeveProjection(
            cash=_decimal(sleeve_raw.get("cash"), f"{prefix}.cash"),
            realized_pnl=_decimal(sleeve_raw.get("realized_pnl"), f"{prefix}.realized_pnl"),
            reserved=_decimal(sleeve_raw.get("reserved"), f"{prefix}.reserved"),
            positions=positions,
        )
    projection = AccountProjection(
        sleeves=sleeves,
        poison_events=_integer(proj_raw.get("poison_events"), "poison_events"),
    )

    res_raw = _mapping(root.get("reservations"), "reservations")
    pending: dict[str, tuple[str, Decimal]] = {}
    for coid, entry_value in _mapping(res_raw.get("pending"), "pending").items():
        entry = _mapping(entry_value, f"pending[{coid}]")
        pending[str(coid)] = (
            _string(entry.get("sleeve_id"), f"pending[{coid}].sleeve_id"),
            _decimal(entry.get("amount"), f"pending[{coid}].amount"),
        )
    terminal_raw = res_raw.get("terminal")
    if not isinstance(terminal_raw, list):
        raise CheckpointStateError(f"terminal: expected list, got {type(terminal_raw).__name__}")
    terminal = dict.fromkeys(_string(item, "terminal[]") for item in terminal_raw)
    return projection, ReservationState(pending=pending, terminal=terminal)


def encode_lots(lots: AccountLotBook) -> dict[str, Any]:
    """Serialize the FIFO lot book to a deterministic JSON-compatible dict.

    Sleeve ids and symbols are sorted; the lots within a symbol keep their FIFO
    (``opened_seq``) order, which is meaningful and must survive the round trip.
    """
    return {
        sleeve_id: {
            symbol: [
                {
                    "qty": str(lot.qty),
                    "cost_basis": str(lot.cost_basis),
                    "opened_seq": lot.opened_seq,
                }
                for lot in symbol_lots
            ]
            for symbol, symbol_lots in sorted(symbols.items())
        }
        for sleeve_id, symbols in sorted(lots.items())
    }


def decode_lots(raw: object) -> AccountLotBook:
    """Strictly deserialize :func:`encode_lots` output; ``None`` → an empty book.

    A checkpoint written before the lot book existed (or one whose lots section
    is absent) yields an empty book, so the caller folds the lot book from the
    seed sequence — never a wrong seed.
    """
    if raw is None:
        return {}
    book: AccountLotBook = {}
    for sleeve_id, symbols in _mapping(raw, "lots").items():
        sleeve_book: dict[str, list[Lot]] = {}
        for symbol, lot_list in _mapping(symbols, f"lots[{sleeve_id}]").items():
            if not isinstance(lot_list, list):
                raise CheckpointStateError(
                    f"lots[{sleeve_id}][{symbol}]: expected list, got {type(lot_list).__name__}"
                )
            parsed: list[Lot] = []
            for index, entry in enumerate(lot_list):
                loc = f"lots[{sleeve_id}][{symbol}][{index}]"
                entry_map = _mapping(entry, loc)
                parsed.append(
                    Lot(
                        qty=_decimal(entry_map.get("qty"), f"{loc}.qty"),
                        cost_basis=_decimal(entry_map.get("cost_basis"), f"{loc}.cost_basis"),
                        opened_seq=_integer(entry_map.get("opened_seq"), f"{loc}.opened_seq"),
                    )
                )
            sleeve_book[str(symbol)] = parsed
        book[str(sleeve_id)] = sleeve_book
    return book


async def load(
    session: AsyncSession, tenant_id: UUID, account_id: UUID
) -> tuple[int, AccountProjection, ReservationState, AccountLotBook] | None:
    """Load the account's persisted checkpoint; ``None`` when absent or unreadable.

    A corrupt/unreadable state row degrades to a full re-fold (warning, never a
    crash) — the row is derived state and the next persisted checkpoint at an
    equal-or-higher sequence repairs it.
    """
    row = await session.scalar(
        select(ProjectionCheckpoint)
        .where(ProjectionCheckpoint.tenant_id == tenant_id)
        .where(ProjectionCheckpoint.account_id == account_id)
    )
    if row is None:
        return None
    try:
        projection, reservations = decode_state(row.state)
        lots = decode_lots(row.state.get("lots"))
    except KeyError, TypeError, ValueError, ArithmeticError:
        logger.warning(
            "unreadable ledger projection checkpoint for account %s (seq=%s); "
            "falling back to a full fold",
            account_id,
            row.as_of_sequence,
            exc_info=True,
        )
        return None
    return int(row.as_of_sequence), projection, reservations, lots


async def save(
    session: AsyncSession,
    tenant_id: UUID,
    account_id: UUID,
    as_of_sequence: int,
    projection: AccountProjection,
    reservations: ReservationState,
    lots: AccountLotBook,
) -> None:
    """Upsert the account's checkpoint, forward-only; does not commit.

    ``ON CONFLICT`` advances the row only when ``as_of_sequence`` is >= the
    stored one, so a stale writer can never regress a checkpoint (``<=`` rather
    than ``<`` lets an equal-sequence save repair a corrupt state row). The
    caller owns the transaction boundary.
    """
    state = encode_state(projection, reservations)
    state["lots"] = encode_lots(lots)
    stmt = (
        pg_insert(ProjectionCheckpoint)
        .values(
            tenant_id=tenant_id,
            account_id=account_id,
            as_of_sequence=as_of_sequence,
            state=state,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "account_id"],
            set_={"as_of_sequence": as_of_sequence, "state": state, "updated_at": func.now()},
            where=ProjectionCheckpoint.as_of_sequence <= as_of_sequence,
        )
    )
    await session.execute(stmt)
