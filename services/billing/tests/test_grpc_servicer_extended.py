"""Extended tests for BillingServicer to improve coverage."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_db.models import Plan, Subscription
from llamatrade_proto.generated import billing_pb2, common_pb2

from src.grpc.servicer import BillingServicer

# === Test Constants ===

TEST_TENANT_ID = uuid4()
TEST_USER_ID = uuid4()


# === Test Fixtures ===


@pytest.fixture
def servicer():
    """BillingServicer with a mock session factory (the RLS set_config is a no-op)."""
    servicer = BillingServicer()
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    servicer._session_maker = cast(Any, lambda: session)
    return servicer


@pytest.fixture
def auth_context() -> common_pb2.TenantContext:
    """Wire identity a unit-test request carries (trusted absent AuthMiddleware)."""
    return common_pb2.TenantContext(tenant_id=str(TEST_TENANT_ID), user_id=str(TEST_USER_ID))


@pytest.fixture
def sample_plan() -> Plan:
    """Create a sample Plan DB row."""
    return Plan(
        name="starter",
        display_name="Starter",
        tier=billing_pb2.PLAN_TIER_STARTER,
        price_monthly=Decimal("29"),
        price_yearly=Decimal("290"),
        features={"backtests": True, "live_trading": False},
        limits={"backtests_per_month": 50, "live_strategies": 1},
        trial_days=14,
    )


@pytest.fixture
def sample_subscription(sample_plan: Plan) -> Subscription:
    """Create a sample Subscription DB row (with its plan attached)."""
    now = datetime.now(UTC)
    sub = Subscription(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        plan_id=uuid4(),
        status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=False,
        trial_start=None,
        trial_end=None,
        canceled_at=None,
        stripe_subscription_id="sub_123",
        stripe_customer_id="cus_123",
        created_at=now,
        updated_at=now,
    )
    sub.plan = sample_plan
    return sub


# === Auth Tests ===


class TestAuthRequired:
    """Identity is resolved from the request context via resolve_identity_connect."""

    @pytest.mark.asyncio
    async def test_missing_context_is_unauthenticated(self, servicer):
        """A request with an empty (nil-UUID) context is rejected UNAUTHENTICATED."""
        from connectrpc.errors import ConnectError

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_subscription(billing_pb2.GetSubscriptionRequest(), MagicMock())
        assert "UNAUTHENTICATED" in str(exc_info.value.code)


# === get_subscription Tests ===


class TestGetSubscription:
    """Tests for get_subscription method."""

    @pytest.mark.asyncio
    async def test_get_subscription_success(self, servicer, auth_context, sample_subscription):
        """Test getting subscription successfully."""
        from llamatrade_proto.generated import billing_pb2

        mock_service = MagicMock()
        mock_service.get_subscription = AsyncMock(return_value=sample_subscription)

        with patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()):
            with patch(
                "src.services.billing_service.BillingService",
                return_value=mock_service,
            ):
                request = billing_pb2.GetSubscriptionRequest(context=auth_context)
                response = await servicer.get_subscription(request, MagicMock())

                assert response.subscription is not None


# === get_usage Tests ===


class _FakeUsageSession:
    """Async session stub that routes count/sum queries by target table."""

    def __init__(self, counts, subscription=None):
        self._counts = counts
        self._subscription = subscription
        self.seen: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, statement):
        sql = str(statement)
        self.seen.append(sql)
        if "subscriptions" in sql:
            return self._subscription
        if "strategy_executions" in sql:
            return self._counts["active_strategies"]
        if "trading_sessions" in sql:
            return self._counts["live_sessions"]
        if "agent_sessions" in sql:
            return self._counts["api_calls"]
        if "backtests" in sql:
            return self._counts["backtests_run"]
        if "strategies" in sql:
            return self._counts["strategies_created"]
        raise AssertionError(f"unexpected usage query: {sql}")

    async def execute(self, *args, **kwargs):
        return None


class TestGetUsage:
    """Tests for get_usage method."""

    @pytest.mark.asyncio
    async def test_get_usage_returns_real_counts(self, servicer, auth_context):
        """Usage maps each server-side count onto the right proto field."""
        from types import SimpleNamespace

        from llamatrade_proto.generated import billing_pb2

        counts = {
            "strategies_created": 6,
            "active_strategies": 3,
            "backtests_run": 6,
            "live_sessions": 3,
            "api_calls": 12,
        }
        subscription = SimpleNamespace(
            current_period_start=datetime(2026, 7, 1, tzinfo=UTC),
            current_period_end=datetime(2026, 8, 1, tzinfo=UTC),
        )
        fake_db = _FakeUsageSession(counts, subscription)

        servicer._session_maker = cast(Any, lambda: fake_db)
        request = billing_pb2.GetUsageRequest(context=auth_context, period_id="")
        response = await servicer.get_usage(request, MagicMock())

        usage = response.usage
        assert usage.tenant_id == str(TEST_TENANT_ID)
        assert usage.strategies_created == 6
        assert usage.active_strategies == 3
        assert usage.backtests_run == 6
        assert usage.live_sessions == 3
        assert usage.api_calls == 12
        assert usage.period_id == "2026-07"
        assert usage.period_start.seconds == int(subscription.current_period_start.timestamp())
        assert usage.period_end.seconds == int(subscription.current_period_end.timestamp())

    @pytest.mark.asyncio
    async def test_get_usage_defaults_to_calendar_month_without_subscription(
        self, servicer, auth_context
    ):
        """With no subscription the period falls back to the calendar month."""
        from llamatrade_proto.generated import billing_pb2

        counts = {
            "strategies_created": 0,
            "active_strategies": 0,
            "backtests_run": 0,
            "live_sessions": 0,
            "api_calls": 0,
        }
        fake_db = _FakeUsageSession(counts, subscription=None)

        servicer._session_maker = cast(Any, lambda: fake_db)
        request = billing_pb2.GetUsageRequest(context=auth_context, period_id="current")
        response = await servicer.get_usage(request, MagicMock())

        usage = response.usage
        assert usage.strategies_created == 0
        assert usage.period_start.seconds > 0
        assert usage.period_end.seconds > usage.period_start.seconds
        # period_id derived as YYYY-MM of the period start
        assert len(usage.period_id) == 7 and usage.period_id[4] == "-"

    @pytest.mark.asyncio
    async def test_get_usage_queries_all_source_tables(self, servicer, auth_context):
        """Every meter is sourced from its own tenant-scoped table."""
        from llamatrade_proto.generated import billing_pb2

        counts = dict.fromkeys(
            [
                "strategies_created",
                "active_strategies",
                "backtests_run",
                "live_sessions",
                "api_calls",
            ],
            0,
        )
        fake_db = _FakeUsageSession(counts, subscription=None)

        servicer._session_maker = cast(Any, lambda: fake_db)
        await servicer.get_usage(
            billing_pb2.GetUsageRequest(context=auth_context, period_id="current"), MagicMock()
        )

        joined = " ".join(fake_db.seen)
        for table in (
            "strategies",
            "strategy_executions",
            "backtests",
            "trading_sessions",
            "agent_sessions",
            "subscriptions",
        ):
            assert table in joined
        # Every query is tenant-scoped.
        assert all("tenant_id" in sql for sql in fake_db.seen)


# === list_invoices Tests ===


class _EmptyInvoicesSession:
    """Async session stub for list_invoices: zero count, no rows."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, statement):
        return 0

    async def execute(self, *args, **kwargs):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result


class TestListInvoices:
    """Tests for list_invoices method."""

    @pytest.mark.asyncio
    async def test_list_invoices_returns_empty(self, servicer, auth_context):
        """Test listing invoices returns an empty page for a tenant with none."""
        from llamatrade_proto.generated import billing_pb2

        servicer._session_maker = cast(Any, lambda: _EmptyInvoicesSession())
        request = billing_pb2.ListInvoicesRequest(context=auth_context)
        response = await servicer.list_invoices(request, MagicMock())

        assert len(response.invoices) == 0
        assert response.pagination.total_items == 0


# === get_invoice Tests ===


class _FakeScalarSession:
    """Async session stub returning a fixed value from scalar()."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, statement):
        return self._value

    async def execute(self, *args, **kwargs):
        return None


def _fake_invoice(invoice_id, tenant_id):
    """Build an invoice-like row with all fields invoice_to_proto reads."""
    from decimal import Decimal
    from types import SimpleNamespace

    from llamatrade_proto.generated import billing_pb2

    now = datetime.now(UTC)
    return SimpleNamespace(
        id=invoice_id,
        tenant_id=tenant_id,
        subscription_id=None,
        amount_due=Decimal("49.00"),
        amount_paid=Decimal("49.00"),
        currency="usd",
        status=billing_pb2.INVOICE_STATUS_PAID,
        period_start=now - timedelta(days=30),
        period_end=now,
        due_date=now,
        paid_at=now,
        invoice_pdf="https://pdf.example/inv.pdf",
        stripe_invoice_id="in_demo_123",
        line_items=[{"description": "Pro plan", "amount": "49.00"}],
    )


class TestGetInvoice:
    """Tests for get_invoice method."""

    @pytest.mark.asyncio
    async def test_get_invoice_not_found_non_uuid(self, servicer, auth_context):
        """A non-UUID invoice id resolves to NOT_FOUND without touching the DB."""
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.GetInvoiceRequest(context=auth_context, invoice_id="inv_123")

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_invoice(request, MagicMock())
        assert "Invoice not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_invoice_not_found_missing_row(self, servicer, auth_context):
        """A valid UUID with no matching row resolves to NOT_FOUND."""
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.GetInvoiceRequest(context=auth_context, invoice_id=str(uuid4()))
        fake_db = _FakeScalarSession(None)

        servicer._session_maker = cast(Any, lambda: fake_db)
        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_invoice(request, MagicMock())
        assert "Invoice not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_invoice_returns_row(self, servicer, auth_context):
        """A matching invoice is mapped to proto and returned."""
        from llamatrade_proto.generated import billing_pb2

        invoice_id = uuid4()
        invoice = _fake_invoice(invoice_id, TEST_TENANT_ID)
        fake_db = _FakeScalarSession(invoice)

        servicer._session_maker = cast(Any, lambda: fake_db)
        request = billing_pb2.GetInvoiceRequest(context=auth_context, invoice_id=str(invoice_id))
        response = await servicer.get_invoice(request, MagicMock())

        assert response.invoice.id == str(invoice_id)
        assert response.invoice.tenant_id == str(TEST_TENANT_ID)
        assert response.invoice.amount_paid.amount == "49.00"
        assert response.invoice.stripe_invoice_id == "in_demo_123"
        assert response.invoice.status == billing_pb2.INVOICE_STATUS_PAID


# === list_plans Tests ===


class TestListPlans:
    """Tests for list_plans method."""

    @pytest.mark.asyncio
    async def test_list_plans_success(self, servicer, sample_plan):
        """Test listing plans successfully (global catalog — not tenant-scoped)."""
        from llamatrade_proto.generated import billing_pb2

        mock_service = MagicMock()
        mock_service.list_plans = AsyncMock(return_value=[sample_plan])

        with patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()):
            with patch(
                "src.services.billing_service.BillingService",
                return_value=mock_service,
            ):
                request = billing_pb2.ListPlansRequest()
                response = await servicer.list_plans(request, MagicMock())

                assert len(response.plans) == 1


# === create_checkout_session Tests ===


class TestCreateCheckoutSession:
    """Failure branches for create_checkout_session (happy path: test_grpc_billing.py)."""

    @pytest.mark.asyncio
    async def test_unknown_plan_raises_not_found(self, servicer, auth_context):
        """Test an unknown plan_id surfaces NOT_FOUND rather than reaching Stripe."""
        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.CreateCheckoutSessionRequest(context=auth_context, plan_id="nope")

        with (
            patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()),
            patch(
                "src.services.billing_service.BillingService.get_plan_db",
                AsyncMock(return_value=None),
            ),
            pytest.raises(ConnectError) as exc,
        ):
            await servicer.create_checkout_session(request, MagicMock())

        assert exc.value.code == Code.NOT_FOUND

    @pytest.mark.asyncio
    async def test_plan_without_price_raises_failed_precondition(self, servicer, auth_context):
        """Test a plan with no Stripe price for the interval fails before calling Stripe."""
        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.CreateCheckoutSessionRequest(
            context=auth_context,
            plan_id="pro",
            interval=billing_pb2.BILLING_INTERVAL_MONTHLY,
        )
        plan = MagicMock(stripe_price_id_monthly="", stripe_price_id_yearly="", trial_days=0)

        with (
            patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()),
            patch(
                "src.services.billing_service.BillingService.get_plan_db",
                AsyncMock(return_value=plan),
            ),
            pytest.raises(ConnectError) as exc,
        ):
            await servicer.create_checkout_session(request, MagicMock())

        assert exc.value.code == Code.FAILED_PRECONDITION
