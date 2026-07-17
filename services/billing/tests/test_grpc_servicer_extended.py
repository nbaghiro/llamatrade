"""Extended tests for BillingServicer to improve coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest

from llamatrade_proto.generated import billing_pb2

from src.grpc.servicer import BillingServicer
from src.models import (
    PlanResponse,
    SubscriptionResponse,
)

# === Test Constants ===

TEST_JWT_SECRET = "test-secret-key-for-testing"
TEST_TENANT_ID = uuid4()
TEST_USER_ID = uuid4()


def create_test_token(tenant_id=None, expired=False):
    """Create a test JWT token."""
    exp = datetime.now(UTC) + timedelta(hours=-1 if expired else 1)
    payload = {
        "sub": str(TEST_USER_ID),
        "tenant_id": str(tenant_id or TEST_TENANT_ID),
        "exp": exp,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


# === Test Fixtures ===


@pytest.fixture
def servicer():
    """BillingServicer with a mock session factory (the RLS set_config is a no-op)."""
    with patch.dict("os.environ", {"JWT_SECRET": TEST_JWT_SECRET}):
        servicer = BillingServicer()
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    servicer._session_maker = lambda: session
    return servicer


@pytest.fixture
def mock_ctx():
    """Create a mock context with auth header."""
    ctx = MagicMock()
    token = create_test_token()
    ctx.request_headers.return_value = {"authorization": f"Bearer {token}"}
    return ctx


@pytest.fixture
def mock_ctx_no_auth():
    """Create a mock context without auth."""
    ctx = MagicMock()
    ctx.request_headers.return_value = {}
    return ctx


@pytest.fixture
def mock_ctx_expired():
    """Create a mock context with expired token."""
    ctx = MagicMock()
    token = create_test_token(expired=True)
    ctx.request_headers.return_value = {"authorization": f"Bearer {token}"}
    return ctx


@pytest.fixture
def sample_plan():
    """Create a sample PlanResponse."""
    return PlanResponse(
        id="starter",
        name="Starter",
        tier=billing_pb2.PLAN_TIER_STARTER,
        price_monthly=29,
        price_yearly=290,
        features={"backtests": True, "live_trading": False},
        limits={"backtests_per_month": 50, "live_strategies": 1},
        trial_days=14,
    )


@pytest.fixture
def sample_subscription(sample_plan):
    """Create a sample SubscriptionResponse."""
    now = datetime.now(UTC)
    return SubscriptionResponse(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        plan=sample_plan,
        status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=False,
        trial_start=None,
        trial_end=None,
        stripe_subscription_id="sub_123",
        created_at=now,
    )


# === _get_tenant_id Tests ===


class TestGetTenantId:
    """Tests for _get_tenant_id method."""

    def test_get_tenant_id_success(self, servicer, mock_ctx):
        """Test extracting tenant ID from valid token."""
        # Mock the JWT decode directly to avoid secret key issues
        with patch("src.grpc.servicer.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": str(TEST_USER_ID),
                "tenant_id": str(TEST_TENANT_ID),
            }
            tenant_id = servicer._get_tenant_id(mock_ctx)
            assert tenant_id == TEST_TENANT_ID

    def test_get_tenant_id_no_auth(self, servicer, mock_ctx_no_auth):
        """Test missing authorization header."""
        from connectrpc.errors import ConnectError

        with pytest.raises(ConnectError) as exc_info:
            servicer._get_tenant_id(mock_ctx_no_auth)
        assert "Missing or invalid authorization" in str(exc_info.value)

    def test_get_tenant_id_invalid_token(self, servicer):
        """Test invalid token."""
        from connectrpc.errors import ConnectError

        ctx = MagicMock()
        ctx.request_headers.return_value = {"authorization": "Bearer invalid-token"}

        with pytest.raises(ConnectError) as exc_info:
            servicer._get_tenant_id(ctx)
        assert "Invalid token" in str(exc_info.value)


# === get_subscription Tests ===


class TestGetSubscription:
    """Tests for get_subscription method."""

    @pytest.mark.asyncio
    async def test_get_subscription_success(self, servicer, mock_ctx, sample_subscription):
        """Test getting subscription successfully."""
        from llamatrade_proto.generated import billing_pb2

        mock_service = MagicMock()
        mock_service.get_subscription = AsyncMock(return_value=sample_subscription)

        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            with patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()):
                with patch(
                    "src.services.billing_service.BillingService",
                    return_value=mock_service,
                ):
                    request = billing_pb2.GetSubscriptionRequest()
                    response = await servicer.get_subscription(request, mock_ctx)

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
    async def test_get_usage_returns_real_counts(self, servicer, mock_ctx):
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

        servicer._session_maker = lambda: fake_db
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.GetUsageRequest(period_id="")
            response = await servicer.get_usage(request, mock_ctx)

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
        self, servicer, mock_ctx
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

        servicer._session_maker = lambda: fake_db
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.GetUsageRequest(period_id="current")
            response = await servicer.get_usage(request, mock_ctx)

        usage = response.usage
        assert usage.strategies_created == 0
        assert usage.period_start.seconds > 0
        assert usage.period_end.seconds > usage.period_start.seconds
        # period_id derived as YYYY-MM of the period start
        assert len(usage.period_id) == 7 and usage.period_id[4] == "-"

    @pytest.mark.asyncio
    async def test_get_usage_queries_all_source_tables(self, servicer, mock_ctx):
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

        servicer._session_maker = lambda: fake_db
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            await servicer.get_usage(billing_pb2.GetUsageRequest(period_id="current"), mock_ctx)

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
    async def test_list_invoices_returns_empty(self, servicer, mock_ctx):
        """Test listing invoices returns an empty page for a tenant with none."""
        from llamatrade_proto.generated import billing_pb2

        servicer._session_maker = lambda: _EmptyInvoicesSession()
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.ListInvoicesRequest()
            response = await servicer.list_invoices(request, mock_ctx)

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
    """Build an invoice-like row with all fields _to_proto_invoice reads."""
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
    async def test_get_invoice_not_found_non_uuid(self, servicer, mock_ctx):
        """A non-UUID invoice id resolves to NOT_FOUND without touching the DB."""
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.GetInvoiceRequest(invoice_id="inv_123")

        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            with pytest.raises(ConnectError) as exc_info:
                await servicer.get_invoice(request, mock_ctx)
        assert "Invoice not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_invoice_not_found_missing_row(self, servicer, mock_ctx):
        """A valid UUID with no matching row resolves to NOT_FOUND."""
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated import billing_pb2

        request = billing_pb2.GetInvoiceRequest(invoice_id=str(uuid4()))
        fake_db = _FakeScalarSession(None)

        servicer._session_maker = lambda: fake_db
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            with pytest.raises(ConnectError) as exc_info:
                await servicer.get_invoice(request, mock_ctx)
        assert "Invoice not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_invoice_returns_row(self, servicer, mock_ctx):
        """A matching invoice is mapped to proto and returned."""
        from llamatrade_proto.generated import billing_pb2

        invoice_id = uuid4()
        invoice = _fake_invoice(invoice_id, TEST_TENANT_ID)
        fake_db = _FakeScalarSession(invoice)

        servicer._session_maker = lambda: fake_db
        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.GetInvoiceRequest(invoice_id=str(invoice_id))
            response = await servicer.get_invoice(request, mock_ctx)

        assert response.invoice.id == str(invoice_id)
        assert response.invoice.tenant_id == str(TEST_TENANT_ID)
        assert response.invoice.amount_paid.amount == "49.00"
        assert response.invoice.stripe_invoice_id == "in_demo_123"
        assert response.invoice.status == billing_pb2.INVOICE_STATUS_PAID


# === list_plans Tests ===


class TestListPlans:
    """Tests for list_plans method."""

    @pytest.mark.asyncio
    async def test_list_plans_success(self, servicer, mock_ctx, sample_plan):
        """Test listing plans successfully."""
        from llamatrade_proto.generated import billing_pb2

        mock_service = MagicMock()
        mock_service.list_plans = AsyncMock(return_value=[sample_plan])

        with patch("src.grpc.servicer.get_stripe_client", return_value=MagicMock()):
            with patch(
                "src.services.billing_service.BillingService",
                return_value=mock_service,
            ):
                request = billing_pb2.ListPlansRequest()
                response = await servicer.list_plans(request, mock_ctx)

                assert len(response.plans) == 1


# === create_checkout_session Tests ===


class TestCreateCheckoutSession:
    """Tests for create_checkout_session method."""

    @pytest.mark.asyncio
    async def test_create_checkout_session_returns_placeholder(self, servicer, mock_ctx):
        """Test creating checkout session returns placeholder URL."""
        from llamatrade_proto.generated import billing_pb2

        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.CreateCheckoutSessionRequest(plan_id="pro")
            response = await servicer.create_checkout_session(request, mock_ctx)

            assert "stripe.com" in response.checkout_url
            assert "placeholder" in response.session_id


# === create_portal_session Tests ===


class TestCreatePortalSession:
    """Tests for create_portal_session method."""

    @pytest.mark.asyncio
    async def test_create_portal_session_returns_placeholder(self, servicer, mock_ctx):
        """Test creating portal session returns placeholder URL."""
        from llamatrade_proto.generated import billing_pb2

        with patch.object(servicer, "_get_tenant_id", return_value=TEST_TENANT_ID):
            request = billing_pb2.CreatePortalSessionRequest()
            response = await servicer.create_portal_session(request, mock_ctx)

            assert "stripe.com" in response.portal_url


# === Helper method tests ===


class TestHelperMethods:
    """Tests for helper conversion methods (now pass-through)."""

    def test_to_proto_status(self, servicer):
        """Test status pass-through (already proto int)."""
        assert (
            servicer._to_proto_status(billing_pb2.SUBSCRIPTION_STATUS_ACTIVE)
            == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        )
        assert (
            servicer._to_proto_status(billing_pb2.SUBSCRIPTION_STATUS_TRIALING)
            == billing_pb2.SUBSCRIPTION_STATUS_TRIALING
        )

    def test_to_proto_tier(self, servicer):
        """Test tier pass-through (already proto int)."""
        assert servicer._to_proto_tier(billing_pb2.PLAN_TIER_FREE) == billing_pb2.PLAN_TIER_FREE
        assert servicer._to_proto_tier(billing_pb2.PLAN_TIER_PRO) == billing_pb2.PLAN_TIER_PRO

    def test_to_proto_interval(self, servicer):
        """Test interval pass-through (already proto int)."""
        assert (
            servicer._to_proto_interval(billing_pb2.BILLING_INTERVAL_MONTHLY)
            == billing_pb2.BILLING_INTERVAL_MONTHLY
        )
        assert (
            servicer._to_proto_interval(billing_pb2.BILLING_INTERVAL_YEARLY)
            == billing_pb2.BILLING_INTERVAL_YEARLY
        )

    def test_from_proto_interval(self, servicer):
        """Test interval pass-through (already proto int)."""
        assert (
            servicer._from_proto_interval(billing_pb2.BILLING_INTERVAL_MONTHLY)
            == billing_pb2.BILLING_INTERVAL_MONTHLY
        )
        assert (
            servicer._from_proto_interval(billing_pb2.BILLING_INTERVAL_YEARLY)
            == billing_pb2.BILLING_INTERVAL_YEARLY
        )
