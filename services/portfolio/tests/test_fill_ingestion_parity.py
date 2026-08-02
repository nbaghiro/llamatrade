"""Parity gate for fill ingestion over the events lib's ``StreamConsumer``.

Replays realistic fill sequences through the consumer path production runs
(``fill_retry_policy`` + ``make_entry_handler`` over ``FakeTransport``) and
asserts the resulting ledger state — event rows written, per-account fold
projections, quarantine records (DLQ parks + tenant alerts), ingest metrics,
and partition pause/resume control — byte-for-byte against
``tests/golden/fill_ingestion_parity.json``, which was recorded from the
retired hand-rolled loop at cutover. Any drift from the money path's contract
(per-account FIFO, commit-after-write, retry-forever on transient failures,
quarantine-not-DLQ for poison) fails here first.

The handler folds through an in-memory writer with the production writer's
event-id dedup and the REAL pure ingestion/projection functions
(``enrich_sell_fill`` / ``open_lots`` / ``fold``), so the scenarios exercise
FIFO cost-basis enrichment and quarantine exactly as ``persist_append`` does.
"""

from __future__ import annotations

import contextlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import (
    EventBus,
    FillEvents,
    LedgerFill,
    LedgerReservation,
    decode_envelope,
)
from llamatrade_events.testing import FakeTransport

from src.alerts import LedgerIncident
from src.ledger.ingestion import FillHandler, LedgerAppend, enrich_sell_fill, needs_cost_basis
from src.ledger.projection import fold, open_lots
from src.tasks.fill_ingestion import (
    LEDGER_FILLS_DLQ_STREAM,
    LEDGER_FILLS_STREAM,
    fill_retry_policy,
    make_entry_handler,
)

GOLDEN = Path(__file__).parent / "golden" / "fill_ingestion_parity.json"

TENANT = str(uuid5(NAMESPACE_URL, "llamatrade/parity/tenant"))
ACCOUNT_A = str(uuid5(NAMESPACE_URL, "llamatrade/parity/account-a"))
ACCOUNT_B = str(uuid5(NAMESPACE_URL, "llamatrade/parity/account-b"))
ACCOUNT_C = str(uuid5(NAMESPACE_URL, "llamatrade/parity/account-c"))
SLEEVE_A = str(uuid5(NAMESPACE_URL, "llamatrade/parity/sleeve-a"))
SLEEVE_B = str(uuid5(NAMESPACE_URL, "llamatrade/parity/sleeve-b"))
SLEEVE_C = str(uuid5(NAMESPACE_URL, "llamatrade/parity/sleeve-c"))
_SLEEVES = {ACCOUNT_A: SLEEVE_A, ACCOUNT_B: SLEEVE_B, ACCOUNT_C: SLEEVE_C}
FILLED_AT = "2026-06-12T14:30:00+00:00"


def _fill(account: str, coid: str, side: str, qty: str, price: str, **extra: str) -> LedgerFill:
    return LedgerFill(
        tenant_id=TENANT,
        account_id=account,
        sleeve_id=_SLEEVES[account],
        client_order_id=coid,
        symbol=extra.pop("symbol", "SPY"),
        side=side,
        qty=qty,
        price=price,
        filled_at=FILLED_AT,
        **extra,
    )


def _reservation(account: str, coid: str, event_type: str, **extra: str) -> LedgerReservation:
    return LedgerReservation(
        tenant_id=TENANT,
        account_id=account,
        sleeve_id=_SLEEVES[account],
        client_order_id=coid,
        event_type=event_type,
        symbol=extra.pop("symbol", "SPY"),
        side=extra.pop("side", "buy"),
        **extra,
    )


_Op = tuple[str, LedgerFill | LedgerReservation | bytes]


@dataclass(frozen=True)
class _Scenario:
    name: str
    # Each phase publishes its ops, then runs a FRESH consumer instance over the
    # shared transport — a phase boundary is a restart resuming from the
    # committed offsets.
    phases: tuple[tuple[_Op, ...], ...]
    # client_order_id → number of injected transient handler failures.
    transient_faults: dict[str, int] = field(default_factory=dict)


SCENARIOS: tuple[_Scenario, ...] = (
    _Scenario(
        name="multi_account_interleave",
        phases=(
            (
                (
                    "reservation",
                    _reservation(ACCOUNT_A, "a-1", "order_submitted", reserved="15000"),
                ),
                ("reservation", _reservation(ACCOUNT_B, "b-1", "order_submitted", reserved="8000")),
                (
                    "reservation",
                    _reservation(ACCOUNT_C, "c-1", "order_submitted", reserved="30000"),
                ),
                ("fill", _fill(ACCOUNT_A, "a-1", "buy", "100", "150")),
                ("fill", _fill(ACCOUNT_B, "b-1", "buy", "20", "400")),
                ("fill", _fill(ACCOUNT_C, "c-1", "buy", "100", "300")),
                # Partial-then-terminal: a cancelled order publishes its filled
                # portion as the terminal fill, then the reservation release.
                ("reservation", _reservation(ACCOUNT_A, "a-2", "order_submitted", reserved="7500")),
                ("fill", _fill(ACCOUNT_A, "a-2", "buy", "30", "150")),
                ("reservation", _reservation(ACCOUNT_A, "a-2", "order_cancelled")),
                # Sell without a publisher cost basis → FIFO enrichment at ingestion.
                ("fill", _fill(ACCOUNT_B, "b-2", "sell", "5", "410")),
            ),
        ),
    ),
    _Scenario(
        name="duplicate_redelivery",
        phases=(
            (
                (
                    "reservation",
                    _reservation(ACCOUNT_A, "dup-1", "order_submitted", reserved="5000"),
                ),
                (
                    "reservation",
                    _reservation(ACCOUNT_A, "dup-1", "order_submitted", reserved="5000"),
                ),
                ("fill", _fill(ACCOUNT_A, "dup-1", "buy", "10", "500")),
                ("fill", _fill(ACCOUNT_A, "dup-1", "buy", "10", "500")),
                ("fill", _fill(ACCOUNT_A, "dup-2", "buy", "2", "500")),
            ),
        ),
    ),
    _Scenario(
        name="out_of_order_reservation_after_terminal",
        phases=(
            (
                ("fill", _fill(ACCOUNT_A, "oo-1", "buy", "10", "100")),
                # The late submit must not earmark cash: its release already happened.
                (
                    "reservation",
                    _reservation(ACCOUNT_A, "oo-1", "order_submitted", reserved="1000"),
                ),
            ),
        ),
    ),
    _Scenario(
        name="poison_mid_stream",
        phases=(
            (
                ("fill", _fill(ACCOUNT_A, "good-1", "buy", "10", "100")),
                ("raw", b"\xff\xfe not an envelope"),
                ("reservation", _reservation(ACCOUNT_B, "tele-1", "order_teleported")),
                # Oversell with no resolvable cost basis → quarantined, stream continues.
                ("fill", _fill(ACCOUNT_A, "oversell-1", "sell", "999", "100")),
                ("fill", _fill(ACCOUNT_B, "good-2", "buy", "4", "250")),
                ("fill", _fill(ACCOUNT_A, "good-3", "buy", "6", "110")),
            ),
        ),
    ),
    _Scenario(
        name="transient_db_failure",
        phases=(
            (
                ("fill", _fill(ACCOUNT_A, "t-1", "buy", "10", "100")),
                ("fill", _fill(ACCOUNT_B, "t-2", "buy", "8", "200")),
                ("fill", _fill(ACCOUNT_A, "t-3", "buy", "3", "105")),
            ),
        ),
        transient_faults={"t-2": 2},
    ),
    _Scenario(
        name="restart_resume",
        phases=(
            (
                ("fill", _fill(ACCOUNT_A, "r-1", "buy", "10", "100")),
                ("fill", _fill(ACCOUNT_B, "r-2", "buy", "5", "300")),
            ),
            (
                ("fill", _fill(ACCOUNT_A, "r-3", "sell", "4", "120")),
                ("fill", _fill(ACCOUNT_B, "r-4", "buy", "1", "310")),
            ),
        ),
    ),
)


@dataclass
class _LedgerRow:
    """An in-memory persisted ledger event (satisfies ``LedgerEventLike``)."""

    event_id: UUID
    account_id: str
    sleeve_id: str
    event_type: LedgerEventType
    data: dict[str, Any]


class _InMemoryLedger:
    """The writer's persistence contract without Postgres: appends are
    idempotent on the deterministic ``event_id`` (ON CONFLICT DO NOTHING) and
    kept in arrival order."""

    def __init__(self) -> None:
        self.rows: list[_LedgerRow] = []
        self._seen: set[UUID] = set()

    def append(self, append: LedgerAppend) -> None:
        if append.event_id in self._seen:
            return
        self._seen.add(append.event_id)
        self.rows.append(
            _LedgerRow(
                event_id=append.event_id,
                account_id=str(append.account_id),
                sleeve_id=str(append.sleeve_id),
                event_type=append.event_type,
                data=dict(append.data),
            )
        )

    def account_rows(self, account_id: str) -> list[_LedgerRow]:
        return [r for r in self.rows if r.account_id == account_id]


class _TransientFaults:
    """Raises ``ConnectionError`` the first N times a client_order_id is handled."""

    def __init__(self, remaining: dict[str, int]) -> None:
        self._remaining = dict(remaining)

    def check(self, client_order_id: str) -> None:
        left = self._remaining.get(client_order_id, 0)
        if left > 0:
            self._remaining[client_order_id] = left - 1
            raise ConnectionError("injected db outage")


def _make_parity_handler(ledger: _InMemoryLedger, faults: _TransientFaults) -> FillHandler:
    """``persist_append``'s pure core over the in-memory ledger: transient-fault
    injection first (a failed transaction persists nothing), then FIFO sell
    enrichment against the account's open lots, then the idempotent append."""

    async def handle(append: LedgerAppend) -> None:
        faults.check(str(append.data.get("client_order_id", "")))
        if needs_cost_basis(append):
            lots = open_lots(
                ledger.account_rows(str(append.account_id)),
                str(append.sleeve_id),
                str(append.data["symbol"]),
            )
            append = enrich_sell_fill(append, lots)
        ledger.append(append)

    return handle


class _AlertRecorder:
    def __init__(self) -> None:
        self.alerts: list[dict[str, str]] = []

    async def dispatch(self, tenant_id: UUID, incident: LedgerIncident) -> None:
        self.alerts.append(
            {
                "tenant_id": str(tenant_id),
                "kind": str(incident.kind),
                "client_order_id": str(incident.context.get("client_order_id", "")),
            }
        )


def _dlq_snapshot(transport: FakeTransport) -> list[dict[str, object]]:
    parks: list[dict[str, object]] = []
    for record in transport.records:
        if record.stream != LEDGER_FILLS_DLQ_STREAM:
            continue
        client_order_id: str | None = None
        decodable = False
        with contextlib.suppress(Exception):
            payload = FillEvents.payload(decode_envelope(record.value))
            client_order_id = payload.client_order_id
            decodable = True
        parks.append(
            {"key": record.key, "client_order_id": client_order_id, "decodable": decodable}
        )
    return parks


def _snapshot(
    ledger: _InMemoryLedger,
    transport: FakeTransport,
    alerts: _AlertRecorder,
    ingest: Counter[str],
) -> dict[str, object]:
    projections: dict[str, object] = {}
    for account in (ACCOUNT_A, ACCOUNT_B, ACCOUNT_C):
        rows = ledger.account_rows(account)
        if not rows:
            continue
        projection = fold(rows)
        projections[account] = {
            "poison_events": projection.poison_events,
            "sleeves": {
                sleeve_id: {
                    "cash": str(sleeve.cash),
                    "reserved": str(sleeve.reserved),
                    "realized_pnl": str(sleeve.realized_pnl),
                    "positions": {
                        symbol: {"qty": str(pos.qty), "cost_basis": str(pos.cost_basis)}
                        for symbol, pos in sorted(sleeve.positions.items())
                    },
                }
                for sleeve_id, sleeve in sorted(projection.sleeves.items())
            },
        }
    return {
        "rows": [
            {
                "event_id": str(row.event_id),
                "account_id": row.account_id,
                "sleeve_id": row.sleeve_id,
                "event_type": row.event_type.value,
                "data": row.data,
            }
            for row in ledger.rows
        ],
        "projections": projections,
        "quarantine": {"dlq": _dlq_snapshot(transport), "alerts": list(alerts.alerts)},
        "ingest": dict(sorted(ingest.items())),
        "partition_control": {
            "paused_cursors": [cursor for _s, _g, cursor in transport.pause_calls],
            "resumed_cursors": [cursor for _s, _g, cursor in transport.resume_calls],
        },
    }


async def _publish(fills: FillEvents, ops: tuple[_Op, ...]) -> None:
    for kind, payload in ops:
        if kind == "fill":
            assert isinstance(payload, LedgerFill)
            await fills.publish_fill(payload)
        elif kind == "reservation":
            assert isinstance(payload, LedgerReservation)
            await fills.publish_reservation(payload)
        else:
            assert isinstance(payload, bytes)
            await fills.bus.publish_raw(LEDGER_FILLS_STREAM, payload)


async def _run_scenario(scenario: _Scenario) -> dict[str, object]:
    """Replay one scenario through the production consumer composition and
    snapshot every externally observable outcome."""
    transport = FakeTransport()
    fills = FillEvents(bus=EventBus(transport))
    ledger = _InMemoryLedger()
    handler = _make_parity_handler(ledger, _TransientFaults(scenario.transient_faults))
    alerts = _AlertRecorder()
    ingest: Counter[str] = Counter()

    with (
        patch("src.alerts.get_ledger_alert_dispatcher", return_value=alerts),
        patch("src.metrics.record_ingest", side_effect=lambda status: ingest.update([status])),
    ):
        for ops in scenario.phases:
            await _publish(fills, ops)
            consumer = fills.consumer(
                consumer_name="parity-1",
                policy=fill_retry_policy(fills.bus, base_delay_seconds=0.0, max_delay_seconds=0.0),
            )
            await consumer.run(make_entry_handler(handler))

    _assert_parked_bytes_are_the_consumed_bytes(transport)
    return _snapshot(ledger, transport, alerts, ingest)


def _assert_parked_bytes_are_the_consumed_bytes(transport: FakeTransport) -> None:
    """A quarantined entry parks the ORIGINAL raw bytes (forensics + replay)."""
    published_main = {r.value for r in transport.records if r.stream == LEDGER_FILLS_STREAM}
    for record in transport.records:
        if record.stream == LEDGER_FILLS_DLQ_STREAM:
            assert record.value in published_main


def _load_golden() -> dict[str, dict[str, object]]:
    return json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_matches_recorded_ledger_outcomes(scenario: _Scenario) -> None:
    """The retained consumer path reproduces the hand-rolled loop's recorded
    outcomes exactly (rows, projections, quarantine, metrics, partition control)."""
    assert await _run_scenario(scenario) == _load_golden()[scenario.name]


async def test_transient_failure_retries_in_place_and_never_dead_letters() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "transient_db_failure")
    snapshot = await _run_scenario(scenario)
    quarantine = snapshot["quarantine"]
    assert isinstance(quarantine, dict)
    assert quarantine["dlq"] == []  # a real fill is NEVER dead-lettered
    ingest = snapshot["ingest"]
    assert isinstance(ingest, dict)
    assert ingest["retry"] == 2  # one per failed attempt
    assert ingest["success"] == 3  # every fill converged
    partition_control = snapshot["partition_control"]
    assert isinstance(partition_control, dict)
    assert len(partition_control["paused_cursors"]) == 1  # paused once, not per attempt
    assert partition_control["paused_cursors"] == partition_control["resumed_cursors"]


async def test_poison_mid_stream_quarantines_and_continues() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "poison_mid_stream")
    snapshot = await _run_scenario(scenario)
    quarantine = snapshot["quarantine"]
    assert isinstance(quarantine, dict)
    dlq = quarantine["dlq"]
    assert isinstance(dlq, list)
    # Undecodable → unkeyed; translation poison + quarantined fill → keyed by account.
    assert [(p["key"], p["decodable"]) for p in dlq] == [
        (None, False),
        (ACCOUNT_B, True),
        (ACCOUNT_A, True),
    ]
    assert [a["kind"] for a in quarantine["alerts"]] == ["fill_quarantined"]
    rows = snapshot["rows"]
    assert isinstance(rows, list)
    # The stream continued past every poison entry.
    assert [r["data"]["client_order_id"] for r in rows] == ["good-1", "good-2", "good-3"]
