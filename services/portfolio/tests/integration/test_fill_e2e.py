"""Flagship money-path E2E: real Kafka + real Postgres, no seams mocked.

Collapses the three separately-mocked halves of the fill pipeline — publish
(``FillEvents.publish_fill``), consume (``consume_fill_stream`` as a Kafka
consumer-group member), and ledger fold (``LedgerWriter`` → ``LedgerProjector``)
— into one chain driven by the SAME components production runs. A ``LedgerFill``
proto is produced to a real broker, drained by the real consumer loop, folded
into a real Postgres ledger, and the projection is polled until the money moves.

Each test owns a unique transport namespace (so topics never collide), funds a
sleeve via the real fund/sleeve services (an unfunded buy would drive cash
negative and freeze the sleeve), and tears the consumer task + bus down cleanly.

Requires Docker (Postgres + Kafka via testcontainers); self-skips otherwise.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import LedgerEvent, LedgerEventType, SleeveStatus
from llamatrade_events import EventBus, FillEvents, LedgerFill
from llamatrade_events.transport.kafka import KafkaTransport

from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.repositories import SqlLedgerStore, SqlSleeveRepository
from src.services.fund_service import FundService
from src.services.sleeve_service import SleeveService
from src.tasks.fill_ingestion import (
    LEDGER_FILLS_STREAM,
    PORTFOLIO_LEDGER_GROUP,
    consume_fill_stream,
    make_fill_handler,
)

pytestmark = pytest.mark.integration

D = Decimal
SYMBOL = "SPY"
_POLL_TIMEOUT = 30.0
_POLL_INTERVAL = 0.25


async def _fund_genesis(
    session_factory: async_sessionmaker,
    tenant_id: UUID,
    *,
    deposit: Decimal = D("100000"),
    allocate: Decimal = D("40000"),
) -> tuple[UUID, UUID]:
    """Genesis via the real services: account + base sleeves + a funded strategy sleeve.

    Committed in its own tenant-scoped session so the (separate) consumer session
    sees it. Returns ``(account_id, strategy_sleeve_id)``.
    """
    async with tenant_session(tenant_id, session_factory) as db:
        repo = SqlSleeveRepository(db)
        sleeves = SleeveService(repo)
        account = await sleeves.get_or_create_account(tenant_id, uuid4())
        await sleeves.ensure_base_sleeves(account)
        strategy = await sleeves.get_or_create_strategy_sleeve(
            account, strategy_execution_id=uuid4(), name="E2E Strategy"
        )
        await db.flush()

        fund = FundService(repo, SqlLedgerStore(db))
        await fund.deposit(tenant_id=tenant_id, account_id=account.id, amount=deposit)
        await fund.allocate(
            tenant_id=tenant_id, account_id=account.id, to_sleeve_id=strategy.id, amount=allocate
        )
        account_id, sleeve_id = account.id, strategy.id
        await db.commit()
    return account_id, sleeve_id


def _fill(
    tenant_id: UUID,
    account_id: UUID,
    sleeve_id: UUID,
    *,
    client_order_id: str,
    side: str,
    qty: str,
    price: str,
) -> LedgerFill:
    """A §1 wire fill exactly as trading publishes it (cost_basis left to FIFO)."""
    return LedgerFill(
        tenant_id=str(tenant_id),
        account_id=str(account_id),
        sleeve_id=str(sleeve_id),
        client_order_id=client_order_id,
        symbol=SYMBOL,
        side=side,
        qty=qty,
        price=price,
        filled_at="2026-06-12T14:30:00+00:00",
    )


@contextlib.asynccontextmanager
async def _running_consumer(
    kafka_bootstrap: str, session_factory: async_sessionmaker
) -> AsyncIterator[FillEvents]:
    """A real Kafka producer/consumer pair on a unique namespace, torn down cleanly.

    Yields the ``FillEvents`` producer while the real ``consume_fill_stream`` loop
    drains the topic into the ledger in a background task.
    """
    namespace = f"e2e{uuid4().hex[:12]}"
    fills = FillEvents(bus=EventBus(KafkaTransport(kafka_bootstrap, namespace=namespace)))
    # Create the topic up front so the consumer's earliest-offset join is race-free.
    await fills.bus.ensure_group(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)
    handler = make_fill_handler(session_factory)
    task = asyncio.create_task(consume_fill_stream(fills, handler, consumer_name="c1"))
    try:
        yield fills
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await fills.close()


def _held_qty(projection: AccountProjection, sleeve_id: UUID, symbol: str) -> Decimal | None:
    """The projected quantity a sleeve holds in ``symbol``, or None if it holds none yet."""
    position = projection.sleeve(str(sleeve_id)).positions.get(symbol)
    return position.qty if position is not None else None


async def _poll_projection(
    session_factory: async_sessionmaker,
    tenant_id: UUID,
    account_id: UUID,
    predicate: Callable[[AccountProjection], bool],
    *,
    timeout: float = _POLL_TIMEOUT,
) -> AccountProjection:
    """Re-fold the ledger from a fresh session until ``predicate`` holds (or time out)."""

    async def _wait() -> AccountProjection:
        while True:
            async with tenant_session(tenant_id, session_factory) as db:
                projection = await LedgerProjector(db).project_account(tenant_id, account_id)
            if predicate(projection):
                return projection
            await asyncio.sleep(_POLL_INTERVAL)

    return await asyncio.wait_for(_wait(), timeout=timeout)


async def _sleeve_status(
    session_factory: async_sessionmaker, tenant_id: UUID, sleeve_id: UUID
) -> str | None:
    async with tenant_session(tenant_id, session_factory) as db:
        sleeve = await SqlSleeveRepository(db).get_sleeve(tenant_id, sleeve_id)
    return sleeve.status if sleeve is not None else None


async def _order_filled_count(
    session_factory: async_sessionmaker, tenant_id: UUID, account_id: UUID
) -> int:
    async with tenant_session(tenant_id, session_factory) as db:
        count = await db.scalar(
            select(func.count())
            .select_from(LedgerEvent)
            .where(
                LedgerEvent.account_id == account_id,
                LedgerEvent.event_type == LedgerEventType.ORDER_FILLED.value,
            )
        )
    return int(count or 0)


async def test_buy_fill_folds_into_ledger(
    session_factory: async_sessionmaker, kafka_bootstrap: str
) -> None:
    """(a) A published buy is consumed and folded: position + cost basis land, sleeve stays active."""
    tenant_id = uuid4()
    account_id, sleeve_id = await _fund_genesis(session_factory, tenant_id)

    async with _running_consumer(kafka_bootstrap, session_factory) as fills:
        await fills.publish_fill(
            _fill(
                tenant_id,
                account_id,
                sleeve_id,
                client_order_id="e2e-buy-1",
                side="buy",
                qty="50",
                price="480",
            )
        )
        projection = await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("50"),
        )

    sleeve = projection.sleeve(str(sleeve_id))
    assert sleeve.positions[SYMBOL].qty == D("50")
    assert sleeve.positions[SYMBOL].cost_basis == D("24000")  # 50 × 480
    assert sleeve.cash == D("16000")  # 40000 − 24000
    # The fill stayed within funded cash, so the invariant guard must NOT freeze it.
    assert await _sleeve_status(session_factory, tenant_id, sleeve_id) == SleeveStatus.ACTIVE.value


async def test_duplicate_fill_is_deduped_exactly_once(
    session_factory: async_sessionmaker, kafka_bootstrap: str
) -> None:
    """(b) The same fill published twice folds once — end-to-end exactly-once.

    A re-published fill reuses its ``client_order_id`` → the same deterministic
    ledger ``event_id`` → the writer's ON CONFLICT dedup drops it. A distinct
    *tracer* fill is published AFTER the duplicate on the SAME partition; once the
    tracer's effect is visible the duplicate has certainly been processed, so a
    quantity of 60 (not 110) and exactly two ledger fills prove the dedup.
    """
    tenant_id = uuid4()
    account_id, sleeve_id = await _fund_genesis(session_factory, tenant_id)

    async with _running_consumer(kafka_bootstrap, session_factory) as fills:
        buy = _fill(
            tenant_id,
            account_id,
            sleeve_id,
            client_order_id="e2e-buy-1",
            side="buy",
            qty="50",
            price="480",
        )
        await fills.publish_fill(buy)
        await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("50"),
        )

        # Re-publish the SAME fill (same client_order_id → same event_id), then a
        # distinct tracer that the consumer must apply after it (same partition).
        await fills.publish_fill(buy)
        await fills.publish_fill(
            _fill(
                tenant_id,
                account_id,
                sleeve_id,
                client_order_id="e2e-tracer",
                side="buy",
                qty="10",
                price="480",
            )
        )
        projection = await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("60"),
        )

    sleeve = projection.sleeve(str(sleeve_id))
    assert sleeve.positions[SYMBOL].qty == D("60")  # 50 + 10, NOT 50 + 50 + 10
    assert sleeve.positions[SYMBOL].cost_basis == D("28800")  # 60 × 480
    # Two distinct fills persisted; the duplicate delivery inserted no third row.
    assert await _order_filled_count(session_factory, tenant_id, account_id) == 2


async def test_buy_then_sell_realizes_fifo_pnl(
    session_factory: async_sessionmaker, kafka_bootstrap: str
) -> None:
    """(c) A sell with no cost basis is FIFO-resolved at ingestion: qty, basis, realized P&L, cash."""
    tenant_id = uuid4()
    account_id, sleeve_id = await _fund_genesis(session_factory, tenant_id)

    async with _running_consumer(kafka_bootstrap, session_factory) as fills:
        await fills.publish_fill(
            _fill(
                tenant_id,
                account_id,
                sleeve_id,
                client_order_id="e2e-buy-1",
                side="buy",
                qty="50",
                price="480",
            )
        )
        # Wait for the buy lot to land so the sell's FIFO enrichment can source it.
        await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("50"),
        )

        await fills.publish_fill(
            _fill(
                tenant_id,
                account_id,
                sleeve_id,
                client_order_id="e2e-sell-1",
                side="sell",
                qty="10",
                price="500",
            )
        )
        projection = await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("40"),
        )

    sleeve = projection.sleeve(str(sleeve_id))
    assert sleeve.positions[SYMBOL].qty == D("40")
    assert sleeve.positions[SYMBOL].cost_basis == D("19200")  # 40 × 480 (FIFO)
    assert sleeve.realized_pnl == D("200")  # 10 × (500 − 480)
    assert sleeve.cash == D("21000")  # 40000 − 24000 + 5000
    assert await _sleeve_status(session_factory, tenant_id, sleeve_id) == SleeveStatus.ACTIVE.value


async def test_dual_path_delivery_of_same_order_folds_once(
    session_factory: async_sessionmaker, kafka_bootstrap: str
) -> None:
    """(d) The stream-path and REST-sync-path fills for the SAME order fold once.

    The two paths publish payloads with DIFFERENT bytes (the REST shape carries
    ``order_id`` and its own ``filled_at``), but share the ``client_order_id`` →
    the same deterministic ledger ``event_id`` → one row. A tracer on the same
    partition proves the duplicate had been processed before asserting.
    """
    tenant_id = uuid4()
    account_id, sleeve_id = await _fund_genesis(session_factory, tenant_id)

    async with _running_consumer(kafka_bootstrap, session_factory) as fills:
        stream_shape = _fill(
            tenant_id,
            account_id,
            sleeve_id,
            client_order_id="e2e-dual-1",
            side="buy",
            qty="50",
            price="480",
        )
        rest_shape = _fill(
            tenant_id,
            account_id,
            sleeve_id,
            client_order_id="e2e-dual-1",
            side="buy",
            qty="50",
            price="480",
        )
        rest_shape.order_id = str(uuid4())
        rest_shape.filled_at = "2026-06-12T14:30:02+00:00"
        assert stream_shape.SerializeToString() != rest_shape.SerializeToString()

        await fills.publish_fill(stream_shape)
        await fills.publish_fill(rest_shape)
        await fills.publish_fill(
            _fill(
                tenant_id,
                account_id,
                sleeve_id,
                client_order_id="e2e-dual-tracer",
                side="buy",
                qty="10",
                price="480",
            )
        )
        projection = await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: _held_qty(p, sleeve_id, SYMBOL) == D("60"),
        )

    sleeve = projection.sleeve(str(sleeve_id))
    assert sleeve.positions[SYMBOL].qty == D("60")  # 50 once + tracer 10, NOT 110
    assert sleeve.positions[SYMBOL].cost_basis == D("28800")
    assert sleeve.cash == D("11200")  # 40000 − 24000 − 4800
    assert await _order_filled_count(session_factory, tenant_id, account_id) == 2
    assert await _sleeve_status(session_factory, tenant_id, sleeve_id) == SleeveStatus.ACTIVE.value


async def test_reservation_release_returns_reserved_to_zero_e2e(
    session_factory: async_sessionmaker, kafka_bootstrap: str
) -> None:
    """(e) A §4 submit-reservation followed by trading's reject release nets
    reserved back to zero through the real consumer + fold."""
    from llamatrade_events import LedgerReservation

    tenant_id = uuid4()
    account_id, sleeve_id = await _fund_genesis(session_factory, tenant_id)

    def _reservation(event_type: str, *, reserved: str = "") -> LedgerReservation:
        message = LedgerReservation(
            event_type=event_type,
            tenant_id=str(tenant_id),
            account_id=str(account_id),
            sleeve_id=str(sleeve_id),
            client_order_id="e2e-resv-1",
            symbol=SYMBOL,
            side="buy",
        )
        if reserved:
            message.reserved = reserved
        return message

    async with _running_consumer(kafka_bootstrap, session_factory) as fills:
        await fills.publish_reservation(_reservation("order_submitted", reserved="24000"))
        await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: p.sleeve(str(sleeve_id)).reserved == D("24000"),
        )

        await fills.publish_reservation(_reservation("order_rejected"))
        projection = await _poll_projection(
            session_factory,
            tenant_id,
            account_id,
            lambda p: p.sleeve(str(sleeve_id)).reserved == D("0"),
        )

    sleeve = projection.sleeve(str(sleeve_id))
    assert sleeve.reserved == D("0")
    assert sleeve.cash == D("40000")  # reservations never move value
