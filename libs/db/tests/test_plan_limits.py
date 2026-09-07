"""Plan-limit resolution + enforcement over real SQL on a real (SQLite) schema.

The subscription join, entitled-status predicate, tenant filter, and
latest-subscription ordering all execute for real here (see ``_sqlite_tier``),
so a broken predicate fails instead of being mirrored by a mock.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.base import Base
from llamatrade_db.models.billing import Plan, Subscription
from llamatrade_db.plan_limits import (
    FREE_TIER_LIMITS,
    UNLIMITED,
    PlanLimitExceededError,
    enforce_plan_limit,
    get_plan_limit,
)
from llamatrade_proto.generated import billing_pb2
from tests._sqlite_tier import as_async_session as _db

pytestmark = pytest.mark.asyncio

_TABLES = [Plan.__table__, Subscription.__table__]


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    """A SQLite engine holding only the tables the plan-limit read touches."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
    """A rolled-back session per test, so rows never leak between them."""
    session = sessionmaker(bind=sqlite_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_plan(session: Session, limits: dict[str, int | None]) -> Plan:
    plan = Plan(
        name=f"plan-{uuid4().hex[:12]}",
        display_name="Pro",
        tier=billing_pb2.PLAN_TIER_PRO,
        price_monthly=Decimal("49.00"),
        features={},
        limits=limits,
    )
    session.add(plan)
    session.flush()
    return plan


def _make_subscription(
    session: Session,
    *,
    tenant_id: UUID,
    plan: Plan,
    status: billing_pb2.SubscriptionStatus.ValueType = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
    created_at: datetime | None = None,
) -> Subscription:
    now = datetime.now(UTC)
    sub = Subscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=status,
        billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        created_at=created_at or now,
    )
    session.add(sub)
    session.flush()
    return sub


class TestGetPlanLimit:
    async def test_limit_from_active_plan(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"live_strategies": 5})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        assert await get_plan_limit(_db(db_session), tenant_id, "live_strategies") == 5

    async def test_trialing_subscription_is_entitled(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"backtests_per_month": 100})
        _make_subscription(
            db_session,
            tenant_id=tenant_id,
            plan=plan,
            status=billing_pb2.SUBSCRIPTION_STATUS_TRIALING,
        )

        assert await get_plan_limit(_db(db_session), tenant_id, "backtests_per_month") == 100

    @pytest.mark.parametrize(
        "status",
        [
            billing_pb2.SUBSCRIPTION_STATUS_CANCELED,
            billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE,
            billing_pb2.SUBSCRIPTION_STATUS_PAUSED,
        ],
    )
    async def test_non_entitled_statuses_fall_back_to_free_tier(
        self, db_session: Session, status: billing_pb2.SubscriptionStatus.ValueType
    ) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"live_strategies": 50})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan, status=status)

        limit = await get_plan_limit(_db(db_session), tenant_id, "live_strategies")

        assert limit == FREE_TIER_LIMITS["live_strategies"]

    async def test_null_limit_means_unlimited(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"backtests_per_month": None})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        assert await get_plan_limit(_db(db_session), tenant_id, "backtests_per_month") == UNLIMITED

    async def test_key_absent_from_plan_falls_back_to_free_tier(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"other": 3})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        limit = await get_plan_limit(_db(db_session), tenant_id, "backtests_per_month")

        assert limit == FREE_TIER_LIMITS["backtests_per_month"]

    async def test_no_subscription_falls_back_to_free_tier(self, db_session: Session) -> None:
        limit = await get_plan_limit(_db(db_session), uuid4(), "live_strategies")

        assert limit == FREE_TIER_LIMITS["live_strategies"]

    async def test_unknown_key_without_subscription_is_zero(self, db_session: Session) -> None:
        assert await get_plan_limit(_db(db_session), uuid4(), "not_a_limit") == 0

    async def test_latest_subscription_wins(self, db_session: Session) -> None:
        tenant_id = uuid4()
        now = datetime.now(UTC)
        old_plan = _make_plan(db_session, {"live_strategies": 2})
        new_plan = _make_plan(db_session, {"live_strategies": 20})
        _make_subscription(
            db_session,
            tenant_id=tenant_id,
            plan=old_plan,
            created_at=now - timedelta(days=30),
        )
        _make_subscription(db_session, tenant_id=tenant_id, plan=new_plan, created_at=now)

        assert await get_plan_limit(_db(db_session), tenant_id, "live_strategies") == 20

    async def test_other_tenants_subscription_does_not_leak(self, db_session: Session) -> None:
        tenant_a, tenant_b = uuid4(), uuid4()
        plan = _make_plan(db_session, {"live_strategies": 50})
        _make_subscription(db_session, tenant_id=tenant_b, plan=plan)

        limit = await get_plan_limit(_db(db_session), tenant_a, "live_strategies")

        assert limit == FREE_TIER_LIMITS["live_strategies"]


class TestEnforcePlanLimit:
    async def test_raises_at_limit_with_key_and_limit(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"live_strategies": 2})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        with pytest.raises(PlanLimitExceededError) as excinfo:
            await enforce_plan_limit(_db(db_session), tenant_id, "live_strategies", 2)

        assert excinfo.value.key == "live_strategies"
        assert excinfo.value.limit == 2

    async def test_ok_below_limit(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"live_strategies": 2})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        await enforce_plan_limit(_db(db_session), tenant_id, "live_strategies", 1)

    async def test_never_raises_on_unlimited(self, db_session: Session) -> None:
        tenant_id = uuid4()
        plan = _make_plan(db_session, {"backtests_per_month": None})
        _make_subscription(db_session, tenant_id=tenant_id, plan=plan)

        await enforce_plan_limit(_db(db_session), tenant_id, "backtests_per_month", 10_000_000)
