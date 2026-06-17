"""Ledger pipeline integration tests (real PostgreSQL + Redis).

Exercises the trading → portfolio fill pipeline end to end against the wire
contract (CONTRACTS.md): payloads cross a real Redis channel, are translated
and persisted by the portfolio ingestion path into a real database, and the
resulting projection must satisfy the conservation invariant
``Σ sleeve == broker`` with FIFO cost basis and reservation lifecycle intact.

Trading-side messages are hand-written protos on purpose: this file IS the
wire-contract check, so it must not share builder code with the publisher.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from llamatrade_events import LedgerFill, LedgerReservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_CREDENTIALS_ID = UUID("55555555-5555-5555-5555-555555555555")

D = Decimal


def add_portfolio_service_to_path() -> None:
    """Add the portfolio service to the Python path for ``src.*`` imports."""
    import sys
    from pathlib import Path

    portfolio_path = Path(__file__).parents[3] / "services" / "portfolio"
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in [
            "auth",
            "billing",
            "strategy",
            "backtest",
            "market-data",
            "trading",
            "notification",
        ]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    portfolio_path_str = str(portfolio_path)
    if portfolio_path_str in sys.path:
        sys.path.remove(portfolio_path_str)
    sys.path.insert(0, portfolio_path_str)


add_portfolio_service_to_path()


@pytest.fixture(scope="module", autouse=True)
def setup_portfolio_path():
    """Set up path for portfolio service imports (also called at module load)."""
    add_portfolio_service_to_path()


@pytest.fixture
async def funded_account(db_session: AsyncSession, run_migrations):
    """An account with base sleeves and a $100k-funded strategy sleeve.

    Returns (account, strategy_sleeve, unallocated_sleeve).
    """
    from src.repositories import SqlLedgerStore, SqlSleeveRepository
    from src.services.fund_service import FundService
    from src.services.sleeve_service import SleeveService

    repo = SqlSleeveRepository(db_session)
    sleeves = SleeveService(repo)
    account = await sleeves.get_or_create_account(TEST_TENANT_ID, TEST_CREDENTIALS_ID)
    base = await sleeves.ensure_base_sleeves(account)
    strategy_sleeve = await sleeves.get_or_create_strategy_sleeve(
        account, strategy_execution_id=uuid4(), name="Integration Strategy"
    )
    await db_session.flush()

    fund = FundService(repo, SqlLedgerStore(db_session))
    await fund.deposit(tenant_id=TEST_TENANT_ID, account_id=account.id, amount=D("100000"))
    await fund.allocate(
        tenant_id=TEST_TENANT_ID,
        account_id=account.id,
        to_sleeve_id=strategy_sleeve.id,
        amount=D("40000"),
    )

    from llamatrade_db.models.ledger import SleeveType

    return account, strategy_sleeve, base[SleeveType.UNALLOCATED]


def _fill_payload(account, sleeve, **overrides: str) -> LedgerFill:
    """A §1a wire message exactly as trading publishes it."""
    fields = {
        "tenant_id": str(TEST_TENANT_ID),
        "account_id": str(account.id),
        "sleeve_id": str(sleeve.id),
        "client_order_id": "lt-int-1",
        "symbol": "SPY",
        "side": "buy",
        "qty": "50",
        "price": "480",
        "filled_at": "2026-06-12T14:30:00+00:00",
    }
    fields.update(overrides)
    return LedgerFill(**fields)


def _reservation_payload(account, sleeve, **overrides: str) -> LedgerReservation:
    """A §4 reservation lifecycle wire message."""
    fields = {
        "tenant_id": str(TEST_TENANT_ID),
        "account_id": str(account.id),
        "sleeve_id": str(sleeve.id),
        "client_order_id": "lt-int-1",
        "symbol": "SPY",
        "side": "buy",
    }
    fields.update(overrides)
    return LedgerReservation(**fields)


async def _ingest(db_session: AsyncSession, message: LedgerFill | LedgerReservation) -> None:
    """Run one message through the real ingestion path (translate → persist)."""
    from src.ledger.ingestion import append_from_message
    from src.tasks.fill_ingestion import persist_append

    await persist_append(db_session, append_from_message(message))


class TestLedgerEconomicScenario:
    """Full reservation → buy → FIFO sell lifecycle holds every invariant."""

    async def test_reservation_buy_sell_lifecycle(
        self, db_session: AsyncSession, funded_account
    ) -> None:
        from src.ledger.projector import LedgerProjector

        account, sleeve, unallocated = funded_account
        projector = LedgerProjector(db_session)

        # 1. Reservation on submit earmarks free cash
        await _ingest(
            db_session,
            _reservation_payload(account, sleeve, event_type="order_submitted", reserved="24000"),
        )
        projection = await projector.project_account(TEST_TENANT_ID, account.id)
        assert projection.sleeve(str(sleeve.id)).reserved == D("24000")

        # 2. The fill consumes the reservation and moves cash → position
        await _ingest(db_session, _fill_payload(account, sleeve))
        # Re-delivery is a no-op (idempotency at the writer)
        await _ingest(db_session, _fill_payload(account, sleeve))

        projection = await projector.project_account(TEST_TENANT_ID, account.id)
        sleeve_proj = projection.sleeve(str(sleeve.id))
        assert sleeve_proj.reserved == D("0")
        assert sleeve_proj.positions["SPY"].qty == D("50")
        assert sleeve_proj.cash == D("16000")

        # 3. Sell WITHOUT cost_basis: the consumer resolves FIFO at ingestion
        await _ingest(
            db_session,
            _fill_payload(
                account,
                sleeve,
                client_order_id="lt-int-2",
                side="sell",
                qty="10",
                price="500",
            ),
        )

        projection = await projector.project_account(TEST_TENANT_ID, account.id)
        sleeve_proj = projection.sleeve(str(sleeve.id))
        assert sleeve_proj.positions["SPY"].qty == D("40")
        assert sleeve_proj.positions["SPY"].cost_basis == D("19200")  # 40 × 480
        assert sleeve_proj.realized_pnl == D("200")  # 10 × (500 − 480)
        assert sleeve_proj.cash == D("16000") + D("5000")

        # 4. Conservation: Σ sleeve qty == broker truth; cash sums hold
        assert projection.account_positions() == {"SPY": D("40")}
        assert projection.total_cash() == D("100000") - D("24000") + D("5000")
        assert projection.sleeve(str(unallocated.id)).cash == D("60000")

    async def test_cancel_releases_reservation(
        self, db_session: AsyncSession, funded_account
    ) -> None:
        from src.ledger.projector import LedgerProjector

        account, sleeve, _ = funded_account
        await _ingest(
            db_session,
            _reservation_payload(
                account,
                sleeve,
                client_order_id="lt-int-cancel",
                event_type="order_submitted",
                reserved="9600",
            ),
        )
        await _ingest(
            db_session,
            _reservation_payload(
                account, sleeve, client_order_id="lt-int-cancel", event_type="order_cancelled"
            ),
        )

        projection = await LedgerProjector(db_session).project_account(TEST_TENANT_ID, account.id)
        assert projection.sleeve(str(sleeve.id)).reserved == D("0")
        assert projection.sleeve(str(sleeve.id)).cash == D("40000")  # untouched


class TestBackfillOnboarding:
    """Onboarding seeds the ledger so the invariant holds from day one."""

    async def test_backfill_matches_broker_state(
        self, db_session: AsyncSession, run_migrations
    ) -> None:
        from src.ledger.projector import LedgerProjector
        from src.ports import BrokerHolding, BrokerSnapshot
        from src.repositories import SqlLedgerStore, SqlSleeveRepository
        from src.services.onboarding_service import AccountOnboardingService
        from src.services.sleeve_service import SleeveService

        class FakeBroker:
            async def snapshot(self, tenant_id, account):
                return BrokerSnapshot(
                    cash=D("25000"),
                    holdings=[BrokerHolding(symbol="QQQ", qty=D("30"), avg_price=D("400"))],
                )

        repo = SqlSleeveRepository(db_session)
        onboarding = AccountOnboardingService(
            SleeveService(repo), SqlLedgerStore(db_session), FakeBroker()
        )

        account = await onboarding.onboard(TEST_TENANT_ID, uuid4())
        # Re-onboarding never double-seeds
        await onboarding.onboard(TEST_TENANT_ID, account.credentials_id)

        projection = await LedgerProjector(db_session).project_account(TEST_TENANT_ID, account.id)
        assert projection.total_cash() == D("25000")
        assert projection.account_positions() == {"QQQ": D("30")}


class TestStreamsPipeline:
    """The durable ledger-fills stream path end-to-end on real Redis."""

    async def test_stream_publish_consume_persist_project(
        self, db_session: AsyncSession, funded_account, redis_url: str
    ) -> None:
        from llamatrade_events import EventBus, FillEvents, RedisStreamsTransport

        from src.ledger.projector import LedgerProjector
        from src.tasks.fill_ingestion import (
            LEDGER_FILLS_STREAM,
            PORTFOLIO_LEDGER_GROUP,
            process_stream_entry,
        )

        account, sleeve, _ = funded_account
        ns = f"t{account.id.hex[:8]}"
        fills = FillEvents(bus=EventBus(RedisStreamsTransport(redis_url, namespace=ns)))
        bus = fills.bus
        try:
            await bus.ensure_group(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)

            # Trading side: publish the §1 proto envelope as FillEvents does.
            await fills.publish_fill(_fill_payload(account, sleeve))

            async def handler(append) -> None:
                from src.tasks.fill_ingestion import persist_append

                await persist_append(db_session, append)

            # Portfolio side: consumer group → parse envelope → verdict → ack
            entries = []
            async for entry_id, env in bus.consume_envelopes(
                LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, "test-pod"
            ):
                verdict = await process_stream_entry(handler, FillEvents.payload(env))
                assert verdict == "ack"
                await bus.ack(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, entry_id)
                entries.append(entry_id)
                break

            assert len(entries) == 1
            assert await bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP) == 0

            projection = await LedgerProjector(db_session).project_account(
                TEST_TENANT_ID, account.id
            )
            assert projection.sleeve(str(sleeve.id)).positions["SPY"].qty == D("50")
        finally:
            await fills.close()

    async def test_redelivery_is_deduped_by_writer(
        self, db_session: AsyncSession, funded_account, redis_url: str
    ) -> None:
        """Consuming the same payload twice is a no-op on the second delivery —
        the at-least-once → effective-once property the consumer group relies on
        (the writer dedupes by event_id)."""
        from src.ledger.ingestion import append_from_message
        from src.ledger.projector import LedgerProjector
        from src.tasks.fill_ingestion import persist_append

        account, sleeve, _ = funded_account
        message = _fill_payload(account, sleeve)

        # Same message delivered twice (e.g. consumer-group redelivery on retry)
        await persist_append(db_session, append_from_message(message))
        await persist_append(db_session, append_from_message(message))

        projection = await LedgerProjector(db_session).project_account(TEST_TENANT_ID, account.id)
        assert projection.sleeve(str(sleeve.id)).positions["SPY"].qty == D("50")  # once
