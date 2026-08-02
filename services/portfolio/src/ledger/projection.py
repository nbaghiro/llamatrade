"""Projections derived by folding the append-only ledger.

The ledger event log is the single source of truth; sleeve cash, positions, and
realized P&L are *derived* by folding postings — never mutated independently.
Folding also asserts the conservation invariant on every event, so any
imbalance surfaces immediately.

These are pure functions over an event stream (no DB/IO), so they are cheap to
unit-test and can rebuild any sleeve's state from the log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Protocol, cast

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.postings import Bucket, assert_balanced, build_postings
from src.ledger.sizing import Lot, select_lots_fifo

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Terminal coids tracked FIFO-bounded: the guard only needs ones recent enough for a late ORDER_SUBMITTED to race, so oldest fall out (caps fold cost + checkpoint size). See ``_apply_reservation``.
_TERMINAL_TRACKED = 4096

# Called when an event can't be applied during fold: (event_id, exception).
PoisonHandler = Callable[[str | None, Exception], None]


class LedgerEventLike(Protocol):
    """Minimal shape needed to fold an event (DB row or plain object).

    Read-only properties so ORM rows (``Mapped[str]`` descriptors) and plain
    dataclasses both satisfy the protocol without invariance issues.
    """

    @property
    def event_type(self) -> str | LedgerEventType: ...

    @property
    def data(self) -> dict[str, Any]: ...


@dataclass
class PositionState:
    """A sleeve's holding in one symbol (derived)."""

    qty: Decimal = ZERO
    cost_basis: Decimal = ZERO  # total cost of the remaining qty


@dataclass
class SleeveProjection:
    """Derived state of a single sleeve."""

    cash: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    # Cash earmarked for open buy orders (reservation lifecycle, §4); free cash = cash − reserved.
    reserved: Decimal = ZERO
    positions: dict[str, PositionState] = field(default_factory=dict)


@dataclass
class AccountProjection:
    """Derived state of an account (all its sleeves)."""

    sleeves: dict[str, SleeveProjection] = field(default_factory=dict)
    # Count of poison events skipped while folding; > 0 means balances are INCOMPLETE — read paths surface it (metric + warning) so a degraded projection is never served as whole.
    poison_events: int = 0

    @property
    def is_complete(self) -> bool:
        """False when any poison event was skipped (balances are incomplete)."""
        return self.poison_events == 0

    def sleeve(self, sleeve_id: str) -> SleeveProjection:
        return self.sleeves.setdefault(sleeve_id, SleeveProjection())

    def total_cash(self) -> Decimal:
        return sum((s.cash for s in self.sleeves.values()), ZERO)

    def account_positions(self) -> dict[str, Decimal]:
        """Aggregate share quantity per symbol across all sleeves (vs. broker)."""
        totals: dict[str, Decimal] = {}
        for sleeve in self.sleeves.values():
            for symbol, pos in sleeve.positions.items():
                totals[symbol] = totals.get(symbol, ZERO) + pos.qty
        return {sym: qty for sym, qty in totals.items() if qty != ZERO}


def _coerce(event_type: str | LedgerEventType) -> LedgerEventType:
    return event_type if isinstance(event_type, LedgerEventType) else LedgerEventType(event_type)


@dataclass
class ReservationState:
    """Reservation-lifecycle fold state, carried alongside the projection.

    ``pending`` maps an open reservation's ``client_order_id`` to its
    ``(sleeve_id, amount)``. ``terminal`` is an insertion-ordered set (``dict``
    keys) of the most recent ``client_order_id``s that reached a terminal order
    event, so a late ``ORDER_SUBMITTED`` (reservation racing its own fill) can
    never earmark cash that has no future release. It is bounded FIFO to
    ``_TERMINAL_TRACKED`` entries — the guard only needs recent coids — so it
    can't grow O(all orders ever). Both are part of the incremental checkpoint
    (see ``LedgerProjector``).
    """

    pending: dict[str, tuple[str, Decimal]] = field(default_factory=dict)
    terminal: dict[str, None] = field(default_factory=dict)

    def copy(self) -> ReservationState:
        """Independent copy for checkpointing (entries are immutable)."""
        return ReservationState(pending=dict(self.pending), terminal=dict(self.terminal))


def fold(
    events: Iterable[LedgerEventLike], *, on_error: PoisonHandler | None = None
) -> AccountProjection:
    """Fold a chronological event stream into an :class:`AccountProjection`.

    Each event is applied in isolation: an event whose data can't be parsed or
    balanced (a "poison" event — corrupt payload, missing key, conservation
    violation) is logged and SKIPPED rather than aborting the whole account, so
    one bad event can never make an account's portfolio unreadable. ``on_error``
    (when wired) is called with the offending ``event_id`` for metrics/alerting.
    Postings are validated BEFORE any state mutation, so a skipped event leaves
    the projection untouched.
    """
    acc = AccountProjection()
    fold_into(acc, ReservationState(), events, on_error=on_error)
    return acc


def fold_into(
    acc: AccountProjection,
    reservations: ReservationState,
    events: Iterable[LedgerEventLike],
    *,
    on_error: PoisonHandler | None = None,
) -> int:
    """Apply ``events`` onto an existing projection + reservation state IN PLACE.

    Shared by the full :func:`fold` and the incremental (checkpoint + delta) path
    in :class:`LedgerProjector`, so a fold resumed from a checkpoint is IDENTICAL
    to a fold from zero by construction (the per-event logic lives here, once).
    Returns the highest event ``sequence`` seen (0 if none carry one) — the
    projector uses it to advance its checkpoint.
    """
    max_sequence = 0
    for ev in events:
        seq = getattr(ev, "sequence", None)
        if seq is not None:
            try:
                max_sequence = max(max_sequence, int(seq))
            except TypeError, ValueError:
                pass
        try:
            event_type = _coerce(ev.event_type)
            postings = build_postings(event_type, ev.data)
            if postings:
                assert_balanced(postings)  # conservation checksum — fail before mutating
            # Reservation lifecycle (no postings of its own); applied only after the economic postings above validated.
            _apply_reservation(acc, reservations, event_type, ev.data)
            for p in postings:
                if p.sleeve_id is None:
                    continue  # EXTERNAL — account boundary, not a sleeve balance
                sleeve = acc.sleeve(p.sleeve_id)
                if p.bucket is Bucket.CASH:
                    sleeve.cash += p.amount
                elif p.bucket is Bucket.PNL:
                    sleeve.realized_pnl += -p.amount
                elif p.bucket is Bucket.POSITION and p.symbol is not None:
                    pos = sleeve.positions.setdefault(p.symbol, PositionState())
                    pos.cost_basis += p.amount
                    if p.qty is not None:
                        pos.qty += p.qty
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            acc.poison_events += 1
            event_id = getattr(ev, "event_id", None)
            eid = str(event_id) if event_id is not None else None
            logger.warning("skipping poison ledger event %s during fold: %s", eid, exc)
            if on_error is not None:
                on_error(eid, exc)
    return max_sequence


# Terminal order events that release an open cash reservation.
_RESERVATION_RELEASES = {
    LedgerEventType.ORDER_FILLED,
    LedgerEventType.ORDER_CANCELLED,
    LedgerEventType.ORDER_REJECTED,
}


def _apply_reservation(
    acc: AccountProjection,
    reservations: ReservationState,
    event_type: LedgerEventType,
    data: dict[str, Any],
) -> None:
    """Track the §4 cash-reservation lifecycle (reserve → release/consume).

    ``reserved`` is derived state, not a posting bucket — reservations don't
    move value, they only earmark it, so conservation is untouched. A submission
    arriving after its order's terminal event is a no-op: the release already
    happened, so honoring it would understate free cash forever.
    """
    client_order_id = data.get("client_order_id")
    if client_order_id is None:
        return
    coid = str(client_order_id)

    if event_type is LedgerEventType.ORDER_SUBMITTED and "reserved" in data:
        if coid in reservations.terminal:
            return
        sleeve_id = data.get("sleeve_id")
        if sleeve_id is None:
            return
        amount = Decimal(str(data["reserved"]))
        acc.sleeve(str(sleeve_id)).reserved += amount
        reservations.pending[coid] = (str(sleeve_id), amount)
    elif event_type in _RESERVATION_RELEASES:
        reservations.terminal[coid] = None
        if len(reservations.terminal) > _TERMINAL_TRACKED:
            # FIFO eviction: drop the oldest tracked coid (guard only needs recent ones), keeping the set bounded in fold cost and row size.
            del reservations.terminal[next(iter(reservations.terminal))]
        entry = reservations.pending.pop(coid, None)
        if entry is not None:
            acc.sleeve(entry[0]).reserved -= entry[1]


def _lot_seq(event: LedgerEventLike, index: int) -> int:
    """FIFO ordering key: the ledger sequence when present, else stream position."""
    seq = getattr(event, "sequence", None)
    if seq is None:
        return index
    try:
        return int(seq)
    except TypeError, ValueError:
        return index


def _rebase_split(lots: list[Lot], qty_delta: Decimal) -> list[Lot]:
    """Re-base one symbol's lots across a split: qty scales, cost is untouched.

    A split changes how many shares carry a position, not what the position
    cost, so each lot keeps its own cost basis exactly (nothing is rounded, so
    no drift is possible) and only the share counts scale by
    ``new_total / old_total`` — per-unit cost therefore divides by the ratio.
    Reverse splits are the same arithmetic with a ratio below one, so fractional
    resulting quantities are kept as Decimal rather than rounded. The newest lot
    absorbs any division remainder, so the lot quantities still sum exactly to
    the post-split position the balance fold reports.
    """
    old_total = sum((lot.qty for lot in lots), ZERO)
    new_total = old_total + qty_delta
    if old_total <= ZERO or new_total <= ZERO:
        return []
    rebased: list[Lot] = []
    allocated = ZERO
    for lot in lots[:-1]:
        qty = lot.qty * new_total / old_total
        allocated += qty
        rebased.append(replace(lot, qty=qty))
    rebased.append(replace(lots[-1], qty=new_total - allocated))
    return rebased


# FIFO lot book for a whole account (sleeve_id -> symbol -> open lots); folded incrementally alongside the projection so fill ingestion resolves a sell's cost basis in O(delta), not a full history fold.
AccountLotBook = dict[str, dict[str, list[Lot]]]


def copy_lot_book(book: AccountLotBook) -> AccountLotBook:
    """A private copy of a lot book (``Lot`` is frozen, so lists are shallow-copied)."""
    return {
        sleeve_id: {symbol: list(lots) for symbol, lots in symbols.items()}
        for sleeve_id, symbols in book.items()
    }


def _apply_split(book: AccountLotBook, data: dict[str, Any]) -> None:
    """Apply a ``SPLIT_APPLIED`` payload to the event's sleeve lots for that symbol."""
    sleeve_id = str(data["sleeve_id"])
    symbol = str(data["symbol"])
    lots = book.get(sleeve_id, {}).get(symbol)
    if not lots:
        logger.warning("split of %s has no tracked lots to re-base", symbol)
        return
    book[sleeve_id][symbol] = _rebase_split(lots, Decimal(str(data["qty_delta"])))


def _apply_rename(book: AccountLotBook, data: dict[str, Any], seq: int) -> None:
    """Carry the event sleeve's lots across a ``SYMBOL_CHANGED``, one lot to one lot.

    Each lot keeps its own basis and its original acquisition order, so FIFO
    after a rename still consumes the oldest shares first. A rename of a holding
    whose lots are not in the stream falls back to the payload's own qty and
    cost basis, which is all the basis information that event carries.
    """
    sleeve_book = book.setdefault(str(data["sleeve_id"]), {})
    carried = sleeve_book.pop(str(data["old_symbol"]), [])
    if not carried:
        qty = Decimal(str(data["qty"]))
        if qty == ZERO:
            return
        carried = [Lot(qty=qty, cost_basis=Decimal(str(data["cost_basis"])), opened_seq=seq)]
    new_symbol = str(data["new_symbol"])
    sleeve_book[new_symbol] = sorted(
        sleeve_book.get(new_symbol, []) + carried, key=lambda lot: lot.opened_seq
    )


def _apply_sleeve_close(book: AccountLotBook, data: dict[str, Any], seq: int) -> None:
    """Carry a closing sleeve's lots across a ``SLEEVE_CLOSED``.

    The closing (source) sleeve is emptied — its lots move to the re-home target
    sleeve, which re-opens each carried lot with its own basis and original
    acquisition order, so FIFO after the close still consumes the oldest shares
    first. Newer ``SLEEVE_CLOSED`` events carry a per-lot ``lots`` list; older
    ones carry only the aggregate ``positions``, so those fall back to one
    blended lot per symbol (the prior behavior).
    """
    source = data.get("sleeve_id")
    if source is not None:
        book[str(source)] = {}  # the source sleeve holds nothing after its close
    target = data.get("to_position_sleeve_id")
    if target is None:
        return
    target_book = book.setdefault(str(target), {})
    lots = data.get("lots")
    if lots:
        for entry in cast("list[dict[str, Any]]", lots):
            sym = str(entry["symbol"])
            lot = Lot(
                qty=Decimal(str(entry["qty"])),
                cost_basis=Decimal(str(entry["cost_basis"])),
                opened_seq=int(entry["opened_seq"]),
            )
            target_book[sym] = sorted(
                target_book.get(sym, []) + [lot], key=lambda lot: lot.opened_seq
            )
        return
    for entry in cast("list[dict[str, Any]]", data.get("positions") or []):
        qty = Decimal(str(entry["qty"]))
        if qty == ZERO:
            continue
        sym = str(entry["symbol"])
        lot = Lot(qty=qty, cost_basis=Decimal(str(entry["cost_basis"])), opened_seq=seq)
        target_book[sym] = sorted(target_book.get(sym, []) + [lot], key=lambda lot: lot.opened_seq)


def fold_lots_into(book: AccountLotBook, events: Iterable[LedgerEventLike]) -> int:
    """Fold an event stream into the account's per-(sleeve, symbol) FIFO lot book IN PLACE.

    Shared by the full :func:`open_lots` and the incremental (checkpoint + delta)
    lot resolution in :class:`LedgerProjector`, so a lot fold resumed from a
    checkpoint is IDENTICAL to a fold from zero: a lot's ``opened_seq`` is the
    absolute event ``sequence`` (not the stream position), so FIFO order does not
    depend on where the fold started. Returns the highest event ``sequence`` seen
    (0 if none carry one) so the projector can advance its checkpoint.

    Buys (positive POSITION postings) open lots; sells consume them FIFO. A split
    re-bases, a rename carries lots to the new symbol, a sleeve close carries them
    to the target sleeve — all keyed on the event type, because their legs carry
    no per-lot detail. A sell exceeding the open lots (drift, external trades)
    clears them rather than raising, and an event the balance fold skips as poison
    is skipped here too, so lots and balances derive from the same events.
    """
    max_sequence = 0
    for index, ev in enumerate(events):
        seq_val = getattr(ev, "sequence", None)
        if seq_val is not None:
            try:
                max_sequence = max(max_sequence, int(seq_val))
            except TypeError, ValueError:
                pass
        try:
            event_type = _coerce(ev.event_type)
            seq = _lot_seq(ev, index)
            if event_type is LedgerEventType.SPLIT_APPLIED:
                _apply_split(book, ev.data)
                continue
            if event_type is LedgerEventType.SYMBOL_CHANGED:
                _apply_rename(book, ev.data, seq)
                continue
            if event_type is LedgerEventType.SLEEVE_CLOSED:
                _apply_sleeve_close(book, ev.data, seq)
                continue
            for p in build_postings(event_type, ev.data):
                if (
                    p.bucket is not Bucket.POSITION
                    or p.sleeve_id is None
                    or p.symbol is None
                    or p.qty is None
                    or p.qty == ZERO
                ):
                    continue
                sleeve_book = book.setdefault(p.sleeve_id, {})
                lots = sleeve_book.setdefault(p.symbol, [])
                if p.qty > ZERO:
                    lots.append(Lot(qty=p.qty, cost_basis=p.amount, opened_seq=seq))
                elif -p.qty >= sum((lot.qty for lot in lots), ZERO):
                    sleeve_book[p.symbol] = []
                else:
                    sleeve_book[p.symbol] = select_lots_fifo(lots, -p.qty).remaining_lots
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            logger.warning("skipping unreadable ledger event while folding lots: %s", exc)
    return max_sequence


def open_lots(events: Iterable[LedgerEventLike], sleeve_id: str, symbol: str) -> list[Lot]:
    """Fold the event stream into the open FIFO lots of one (sleeve, symbol).

    A thin wrapper over :func:`fold_lots_into`: it folds the whole account lot
    book from zero and returns the requested (sleeve, symbol) slice, so the full
    fold and the projector's incremental fold share one implementation. Used at
    fill ingestion to resolve the cost basis of a sell when the publisher didn't
    supply one — the resolved value is then written into the event data, so the
    log stays self-contained and replayable.
    """
    book: AccountLotBook = {}
    fold_lots_into(book, events)
    return book.get(sleeve_id, {}).get(symbol, [])


@dataclass
class HoldingHistoryEntry:
    """One provenance-bearing line in a symbol's trade history."""

    sleeve_id: str
    side: str  # "buy" | "sell"
    qty: Decimal  # absolute
    price: Decimal | None
    realized_pnl: Decimal | None
    occurred_at: Any | None


def holding_history(events: Iterable[LedgerEventLike], symbol: str) -> list[HoldingHistoryEntry]:
    """Per-symbol trade timeline with sleeve provenance (the user-facing view)."""
    out: list[HoldingHistoryEntry] = []
    for ev in events:
        postings = build_postings(_coerce(ev.event_type), ev.data)
        for p in postings:
            if p.bucket is not Bucket.POSITION or p.symbol != symbol or p.qty is None:
                continue
            if p.sleeve_id is None:
                continue
            data = ev.data
            price = Decimal(str(data["price"])) if "price" in data else None
            realized = Decimal(str(data["realized_pnl"])) if "realized_pnl" in data else None
            out.append(
                HoldingHistoryEntry(
                    sleeve_id=p.sleeve_id,
                    side="buy" if p.qty > ZERO else "sell",
                    qty=abs(p.qty),
                    price=price,
                    realized_pnl=realized,
                    occurred_at=getattr(ev, "occurred_at", None),
                )
            )
    return out
