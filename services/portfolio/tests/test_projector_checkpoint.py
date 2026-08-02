"""Tests for persisted incremental-projection checkpoints.

Covers deterministic serialization round-trips (property-style over the real
fold), restart equivalence (seed-from-checkpoint + delta == fold-from-zero),
persistence throttling, forward-only advancement, and corrupt/unreadable
checkpoint fallback.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger import checkpoint_store
from src.ledger.checkpoint_store import CheckpointStateError, decode_state, encode_state
from src.ledger.projection import (
    AccountProjection,
    PositionState,
    ReservationState,
    SleeveProjection,
    fold,
    fold_into,
)
from src.ledger.projector import _INCREMENTAL_CACHE, LedgerProjector
from src.ledger.writer import LedgerWriter

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT = UUID("22222222-2222-2222-2222-222222222222")

U = "unalloc"
S1 = "strat-1"
S2 = "strat-2"


@dataclass
class Ev:
    """Minimal sequenced event view for folding (mirrors a LedgerEvent row)."""

    sequence: int
    event_type: LedgerEventType
    data: dict[str, Any]
    event_id: str | None = None


def _gen_events(rng: random.Random, n: int) -> list[Ev]:
    """Random-but-valid ledger stream: deposits, allocations, trades, dividends,
    fees, and reservation lifecycles including a guaranteed open reservation and
    a guaranteed late submission (terminal reached before the submit lands)."""
    events: list[Ev] = []
    coid = 0

    def add(event_type: LedgerEventType, data: dict[str, Any]) -> None:
        events.append(Ev(len(events) + 1, event_type, data))

    add(LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": U, "amount": "100000"})
    for sleeve in (S1, S2):
        add(
            LedgerEventType.CAPITAL_ALLOCATED,
            {"from_sleeve_id": U, "to_sleeve_id": sleeve, "amount": "30000"},
        )
    while len(events) < n - 3:
        sleeve = rng.choice((S1, S2))
        symbol = rng.choice(("SPY", "QQQ"))
        action = rng.randrange(5)
        if action == 0:
            add(
                LedgerEventType.ORDER_FILLED,
                {
                    "sleeve_id": sleeve,
                    "symbol": symbol,
                    "side": "buy",
                    "qty": str(rng.randrange(1, 10)),
                    "price": str(rng.randrange(50, 150)),
                },
            )
        elif action == 1:
            add(
                LedgerEventType.ORDER_FILLED,
                {
                    "sleeve_id": sleeve,
                    "symbol": symbol,
                    "side": "sell",
                    "qty": "2",
                    "price": str(rng.randrange(50, 150)),
                    "cost_basis": str(rng.randrange(100, 300)),
                },
            )
        elif action == 2:
            coid += 1
            cid = f"o{coid}"
            add(
                LedgerEventType.ORDER_SUBMITTED,
                {"sleeve_id": sleeve, "client_order_id": cid, "reserved": "500"},
            )
            add(LedgerEventType.ORDER_CANCELLED, {"sleeve_id": sleeve, "client_order_id": cid})
        elif action == 3:
            add(LedgerEventType.DIVIDEND_RECEIVED, {"sleeve_id": sleeve, "amount": "12"})
        else:
            add(LedgerEventType.FEE_CHARGED, {"sleeve_id": sleeve, "amount": "3"})
    add(
        LedgerEventType.ORDER_SUBMITTED,
        {"sleeve_id": S1, "client_order_id": "open-res", "reserved": "750"},
    )
    add(LedgerEventType.ORDER_CANCELLED, {"sleeve_id": S1, "client_order_id": "late-res"})
    add(
        LedgerEventType.ORDER_SUBMITTED,
        {"sleeve_id": S1, "client_order_id": "late-res", "reserved": "250"},
    )
    return events


def _fold_state(events: list[Ev]) -> tuple[AccountProjection, ReservationState]:
    projection, reservations = AccountProjection(), ReservationState()
    fold_into(projection, reservations, events)
    return projection, reservations


class FakeDb:
    """Duck-typed AsyncSession over one in-memory checkpoint row.

    ``execute`` applies the upsert with the same forward-only ``<=`` predicate
    Postgres evaluates; ``test_save_statement_carries_forward_only_guard``
    asserts the real statement carries it.
    """

    def __init__(self) -> None:
        self.row: SimpleNamespace | None = None
        self.loads = 0
        self.saves = 0
        self.commits = 0
        self.rollbacks = 0
        self.fail_writes = False

    async def scalar(self, stmt: object) -> SimpleNamespace | None:
        self.loads += 1
        return self.row

    async def execute(self, stmt: Any) -> None:
        if self.fail_writes:
            raise SQLAlchemyError("write refused")
        self.saves += 1
        params = stmt.compile(dialect=postgresql.dialect()).params
        sequence, state = params["as_of_sequence"], params["state"]
        if self.row is None or self.row.as_of_sequence <= sequence:
            self.row = SimpleNamespace(as_of_sequence=sequence, state=state)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeWriter:
    """In-memory LedgerWriter read surface over a fixed event list."""

    def __init__(self, events: list[Ev]) -> None:
        self.events = events
        self.reads_after: list[int] = []

    async def read_account_events_since(
        self, tenant_id: UUID, account_id: UUID, after_sequence: int
    ) -> list[Ev]:
        self.reads_after.append(after_sequence)
        return [e for e in self.events if e.sequence > after_sequence]

    async def read_account_events(self, tenant_id: UUID, account_id: UUID) -> list[Ev]:
        return list(self.events)


def _make_projector(events: list[Ev], db: FakeDb) -> tuple[LedgerProjector, FakeWriter]:
    projector = LedgerProjector(cast(AsyncSession, db))
    writer = FakeWriter(events)
    projector._writer = cast(LedgerWriter, writer)
    return projector, writer


@pytest.fixture(autouse=True)
def clear_incremental_cache() -> Iterator[None]:
    _INCREMENTAL_CACHE.clear()
    yield
    _INCREMENTAL_CACHE.clear()


def test_terminal_set_is_bounded_fifo() -> None:
    """Old terminal coids are pruned FIFO; recent ones stay so the late-submit
    guard still no-ops a submission that races its own terminal event."""
    from src.ledger.projection import _TERMINAL_TRACKED

    total = _TERMINAL_TRACKED + 50
    events = [
        Ev(i + 1, LedgerEventType.ORDER_CANCELLED, {"sleeve_id": S1, "client_order_id": f"co-{i}"})
        for i in range(total)
    ]
    projection, reservations = AccountProjection(), ReservationState()
    fold_into(projection, reservations, events)

    assert len(reservations.terminal) == _TERMINAL_TRACKED  # bounded, not O(all orders)
    assert "co-0" not in reservations.terminal  # oldest pruned
    assert f"co-{total - 1}" in reservations.terminal  # most recent retained
    # A submission racing a still-tracked terminal is a no-op (no cash earmarked).
    fold_into(
        projection,
        reservations,
        [
            Ev(
                total + 1,
                LedgerEventType.ORDER_SUBMITTED,
                {"sleeve_id": S1, "client_order_id": f"co-{total - 1}", "reserved": "500"},
            )
        ],
    )
    assert reservations.pending == {} and projection.sleeve(S1).reserved == Decimal("0")


class TestStateSerialization:
    @pytest.mark.parametrize("seed", range(8))
    def test_round_trip_over_random_folds_is_exact(self, seed: int) -> None:
        """encode → JSON wire round-trip → decode reproduces the fold state."""
        events = _gen_events(random.Random(seed), 30)
        projection, reservations = _fold_state(events)
        assert reservations.pending and reservations.terminal  # generator guarantees both
        wire = json.loads(json.dumps(encode_state(projection, reservations)))
        decoded_projection, decoded_reservations = decode_state(wire)
        assert decoded_projection == projection
        assert decoded_reservations == reservations

    def test_empty_state_round_trips(self) -> None:
        projection, reservations = decode_state(
            encode_state(AccountProjection(), ReservationState())
        )
        assert projection == AccountProjection()
        assert reservations == ReservationState()

    def test_encode_is_deterministic_regardless_of_insertion_order(self) -> None:
        def build(reverse: bool) -> dict[str, Any]:
            sleeve_ids = ["b", "a"] if reverse else ["a", "b"]
            symbols = ["SPY", "AAPL"] if reverse else ["AAPL", "SPY"]
            sleeves = {
                sid: SleeveProjection(
                    cash=Decimal("10.50"),
                    positions={sym: PositionState(qty=Decimal("1")) for sym in symbols},
                )
                for sid in sleeve_ids
            }
            reservations = ReservationState(
                pending=dict(
                    reversed([("o1", ("a", Decimal("5"))), ("o2", ("b", Decimal("6")))])
                    if reverse
                    else [("o1", ("a", Decimal("5"))), ("o2", ("b", Decimal("6")))]
                ),
                terminal=dict.fromkeys(["z", "y", "x"]),
            )
            return encode_state(AccountProjection(sleeves=sleeves), reservations)

        assert json.dumps(build(False)) == json.dumps(build(True))

    def test_decimals_preserve_scale_and_sets_sorted(self) -> None:
        projection = AccountProjection(
            sleeves={"s": SleeveProjection(cash=Decimal("100.00"), reserved=Decimal("0.10"))}
        )
        reservations = ReservationState(terminal=dict.fromkeys(["b", "a", "c"]))
        state = encode_state(projection, reservations)
        assert state["projection"]["sleeves"]["s"]["cash"] == "100.00"
        assert state["reservations"]["terminal"] == ["a", "b", "c"]
        decoded, _ = decode_state(state)
        assert str(decoded.sleeves["s"].cash) == "100.00"

    def _valid_state(self) -> dict[str, Any]:
        events = _gen_events(random.Random(0), 12)
        return encode_state(*_fold_state(events))

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda s: s.update(v=99), id="unsupported-version"),
            pytest.param(lambda s: s.pop("v"), id="missing-version"),
            pytest.param(lambda s: s.pop("projection"), id="missing-projection"),
            pytest.param(lambda s: s.pop("reservations"), id="missing-reservations"),
            pytest.param(
                lambda s: s["projection"].update(poison_events="0"), id="stringly-poison-count"
            ),
            pytest.param(
                lambda s: s["projection"].update(poison_events=True), id="bool-poison-count"
            ),
            pytest.param(
                lambda s: s["projection"]["sleeves"][S1].update(cash=100.0), id="float-cash"
            ),
            pytest.param(
                lambda s: s["projection"]["sleeves"][S1].update(cash="not-a-number"),
                id="garbage-decimal",
            ),
            pytest.param(lambda s: s["projection"]["sleeves"][S1].update(cash="NaN"), id="nan"),
            pytest.param(
                lambda s: s["projection"]["sleeves"][S1].update(cash="Infinity"), id="infinity"
            ),
            pytest.param(
                lambda s: s["projection"]["sleeves"][S1].pop("reserved"), id="missing-field"
            ),
            pytest.param(lambda s: s["reservations"].update(terminal="o1"), id="terminal-not-list"),
            pytest.param(
                lambda s: s["reservations"].update(pending={"o9": ["s", "5"]}),
                id="pending-entry-not-object",
            ),
            pytest.param(
                lambda s: s["reservations"]["pending"].update(bad={"sleeve_id": 3, "amount": "5"}),
                id="pending-sleeve-not-string",
            ),
        ],
    )
    def test_strict_decode_rejects_malformed_state(
        self, mutate: Callable[[dict[str, Any]], object]
    ) -> None:
        state = self._valid_state()
        mutate(state)
        with pytest.raises(CheckpointStateError):
            decode_state(state)

    def test_decode_rejects_non_object_root(self) -> None:
        with pytest.raises(CheckpointStateError):
            decode_state(["not", "a", "state"])


class TestCheckpointStoreLoad:
    async def test_absent_row_returns_none(self) -> None:
        db = FakeDb()
        assert await checkpoint_store.load(cast(AsyncSession, db), TENANT, ACCOUNT) is None

    async def test_good_row_returns_state(self) -> None:
        events = _gen_events(random.Random(1), 15)
        projection, reservations = _fold_state(events)
        db = FakeDb()
        db.row = SimpleNamespace(
            as_of_sequence=len(events), state=encode_state(projection, reservations)
        )
        loaded = await checkpoint_store.load(cast(AsyncSession, db), TENANT, ACCOUNT)
        assert loaded is not None
        sequence, loaded_projection, loaded_reservations, loaded_lots = loaded
        assert sequence == len(events)
        assert loaded_projection == projection
        assert loaded_reservations == reservations
        assert loaded_lots == {}  # a state written without a lots section decodes empty

    @pytest.mark.parametrize(
        "state",
        [
            {"v": 99},
            {"v": 1, "projection": {"poison_events": 0, "sleeves": {"s": {"cash": 1.5}}}},
            ["wrong", "shape"],
            "garbage",
        ],
    )
    async def test_unreadable_row_warns_and_returns_none(
        self, state: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = FakeDb()
        db.row = SimpleNamespace(as_of_sequence=7, state=state)
        with caplog.at_level("WARNING"):
            loaded = await checkpoint_store.load(cast(AsyncSession, db), TENANT, ACCOUNT)
        assert loaded is None
        assert "unreadable ledger projection checkpoint" in caplog.text


class TestCheckpointStoreSave:
    async def test_save_statement_carries_forward_only_guard(self) -> None:
        """The real upsert targets (tenant_id, account_id) and only advances."""
        captured: list[Any] = []

        class Recorder(FakeDb):
            async def execute(self, stmt: Any) -> None:
                captured.append(stmt)

        await checkpoint_store.save(
            cast(AsyncSession, Recorder()),
            TENANT,
            ACCOUNT,
            5,
            AccountProjection(),
            ReservationState(),
            {},
        )
        sql = str(captured[0].compile(dialect=postgresql.dialect()))
        assert "INSERT INTO ledger_projection_checkpoints" in sql
        assert "ON CONFLICT (tenant_id, account_id) DO UPDATE" in sql
        assert "ledger_projection_checkpoints.as_of_sequence <=" in sql


class TestIncrementalPersistence:
    async def test_restart_seeds_from_persisted_checkpoint(self) -> None:
        rng = random.Random(42)
        before = _gen_events(rng, 12)
        db = FakeDb()
        warm, _ = _make_projector(before, db)
        await warm.project_account_incremental(TENANT, ACCOUNT)
        assert db.saves == 1 and db.commits == 1
        assert db.row is not None and db.row.as_of_sequence == len(before)

        _INCREMENTAL_CACHE.clear()  # simulated process restart
        after_events = before + [
            Ev(
                len(before) + 1,
                LedgerEventType.DIVIDEND_RECEIVED,
                {"sleeve_id": S1, "amount": "9"},
            )
        ]
        cold, writer = _make_projector(after_events, db)
        resumed = await cold.project_account_incremental(TENANT, ACCOUNT)
        assert resumed == fold(after_events)
        assert writer.reads_after == [len(before)]  # only the delta was read
        assert db.row.as_of_sequence == len(after_events)

    @pytest.mark.parametrize("seed", range(5))
    async def test_restart_equivalence_randomized(self, seed: int) -> None:
        """fold-from-zero == seed-from-persisted-checkpoint + delta, any split."""
        events = _gen_events(random.Random(seed), 24)
        n = len(events)
        full = fold(events)
        for split in sorted({0, 1, n // 3, n // 2, n - 1, n}):
            _INCREMENTAL_CACHE.clear()
            db = FakeDb()
            warm, _ = _make_projector(events[:split], db)
            await warm.project_account_incremental(TENANT, ACCOUNT)
            _INCREMENTAL_CACHE.clear()  # simulated process restart
            cold, writer = _make_projector(events, db)
            resumed = await cold.project_account_incremental(TENANT, ACCOUNT)
            assert resumed == full, f"seed {seed} split {split} diverged from full fold"
            assert writer.reads_after == [split]  # persisted seq == split (or 0)

    async def test_late_reservation_terminal_survives_restart(self) -> None:
        """A terminal recorded before restart still no-ops a late submission after."""
        before = [
            Ev(1, LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": S1, "amount": "1000"}),
            Ev(2, LedgerEventType.ORDER_CANCELLED, {"sleeve_id": S1, "client_order_id": "oL"}),
        ]
        db = FakeDb()
        warm, _ = _make_projector(before, db)
        await warm.project_account_incremental(TENANT, ACCOUNT)

        _INCREMENTAL_CACHE.clear()
        events = before + [
            Ev(
                3,
                LedgerEventType.ORDER_SUBMITTED,
                {"sleeve_id": S1, "client_order_id": "oL", "reserved": "400"},
            )
        ]
        cold, _ = _make_projector(events, db)
        resumed = await cold.project_account_incremental(TENANT, ACCOUNT)
        assert resumed.sleeves[S1].reserved == Decimal("0")
        assert resumed == fold(events)

    async def test_persistence_throttled_when_sequence_unchanged(self) -> None:
        events = _gen_events(random.Random(7), 10)
        db = FakeDb()
        warm, _ = _make_projector(events, db)
        await warm.project_account_incremental(TENANT, ACCOUNT)
        assert (db.saves, db.commits) == (1, 1)

        _INCREMENTAL_CACHE.clear()  # restart with no new events: load, but no re-save
        cold, _ = _make_projector(events, db)
        await cold.project_account_incremental(TENANT, ACCOUNT)
        assert (db.saves, db.commits) == (1, 1)
        loads_after_seed = db.loads

        await cold.project_account_incremental(TENANT, ACCOUNT)  # first-level cache hit
        assert db.loads == loads_after_seed
        assert (db.saves, db.commits) == (1, 1)

    async def test_checkpoint_never_regresses(self) -> None:
        """A checkpoint ahead of this reader's events is left untouched."""
        events = _gen_events(random.Random(3), 10)
        ahead_projection, ahead_reservations = _fold_state(events)
        db = FakeDb()
        db.row = SimpleNamespace(
            as_of_sequence=100, state=encode_state(ahead_projection, ahead_reservations)
        )
        projector, writer = _make_projector(events, db)
        result = await projector.project_account_incremental(TENANT, ACCOUNT)
        assert writer.reads_after == [100]  # seeded from the ahead checkpoint
        assert result == ahead_projection
        assert db.saves == 0 and db.row.as_of_sequence == 100

    async def test_corrupt_checkpoint_full_folds_and_repairs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        events = _gen_events(random.Random(11), 14)
        db = FakeDb()
        db.row = SimpleNamespace(as_of_sequence=3, state={"v": 1, "projection": "corrupt"})
        projector, writer = _make_projector(events, db)
        with caplog.at_level("WARNING"):
            result = await projector.project_account_incremental(TENANT, ACCOUNT)
        assert "unreadable ledger projection checkpoint" in caplog.text
        assert result == fold(events)
        assert writer.reads_after == [0]  # fell back to a full fold
        assert db.row.as_of_sequence == len(events)  # equal-or-forward save repaired the row
        assert decode_state(db.row.state) == _fold_state(events)

    async def test_poisoned_projection_is_never_persisted(self) -> None:
        events = _gen_events(random.Random(5), 8)
        events.append(
            Ev(len(events) + 1, LedgerEventType.ORDER_FILLED, {"sleeve_id": S1, "symbol": "SPY"})
        )
        db = FakeDb()
        projector, _ = _make_projector(events, db)
        result = await projector.project_account_incremental(TENANT, ACCOUNT)
        assert result.poison_events == 1 and not result.is_complete
        assert db.saves == 0 and db.commits == 0  # a restart must re-fold, not inherit the gap

    async def test_persist_failure_degrades_to_unpersisted_projection(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        events = _gen_events(random.Random(9), 10)
        db = FakeDb()
        db.fail_writes = True
        projector, _ = _make_projector(events, db)
        with caplog.at_level("WARNING"):
            result = await projector.project_account_incremental(TENANT, ACCOUNT)
        assert result == fold(events)
        assert "failed to persist ledger projection checkpoint" in caplog.text
        assert db.commits == 0 and db.rollbacks == 1

    async def test_open_lots_incremental_equals_full_fold_after_restart(self) -> None:
        """A basis-less sell resolves FIFO lots from the persisted checkpoint lot
        book + only the delta since it (O(delta)), matching a full fold (F40)."""
        from src.ledger.projection import open_lots

        sleeve = uuid4()
        sid = str(sleeve)
        base = [
            Ev(1, LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": U, "amount": "100000"}),
            Ev(
                2,
                LedgerEventType.CAPITAL_ALLOCATED,
                {"from_sleeve_id": U, "to_sleeve_id": sid, "amount": "50000"},
            ),
            Ev(
                3,
                LedgerEventType.ORDER_FILLED,
                {"sleeve_id": sid, "symbol": "SPY", "side": "buy", "qty": "10", "price": "100"},
            ),
            Ev(
                4,
                LedgerEventType.ORDER_FILLED,
                {"sleeve_id": sid, "symbol": "SPY", "side": "buy", "qty": "5", "price": "120"},
            ),
        ]
        db = FakeDb()
        warm, _ = _make_projector(base, db)
        await warm.project_account_incremental(TENANT, ACCOUNT)  # persists the lot book too
        assert db.row is not None and db.row.as_of_sequence == 4

        _INCREMENTAL_CACHE.clear()  # simulated process restart: cold lot cache
        after = base + [
            Ev(
                5,
                LedgerEventType.ORDER_FILLED,
                {
                    "sleeve_id": sid,
                    "symbol": "SPY",
                    "side": "sell",
                    "qty": "6",
                    "price": "150",
                    "cost_basis": "600",
                },
            )
        ]
        cold, writer = _make_projector(after, db)
        lots = await cold.open_lots_incremental(TENANT, ACCOUNT, sleeve, "SPY")

        assert lots == open_lots(after, sid, "SPY")  # exact FIFO match
        assert writer.reads_after == [4]  # only the delta since the persisted checkpoint
