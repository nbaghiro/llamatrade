"""Test fixtures for billing service tests.

Hosts the two canonical doubles (``MockStripeClient``, spec-checked in
test_mock_stripe_contract.py, and the statement-aware ``MockAsyncSession``),
the shared Stripe webhook payload builders, and the real-SQL-on-SQLite tier
that drives the servicer against a real schema.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncGenerator, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Executable, create_engine, event, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.compiler import GenericTypeCompiler
from sqlalchemy.sql.elements import TextClause
from stripe import Customer, Event
from stripe import Invoice as StripeInvoice
from stripe import PaymentMethod as StripePaymentMethod
from stripe import Subscription as StripeSubscription

from llamatrade_db import get_db
from llamatrade_db.base import Base
from llamatrade_db.models import Invoice, PaymentMethod, Plan, Subscription
from llamatrade_proto.generated import billing_pb2

from src.grpc.servicer import BillingServicer
from src.main import app
from src.stripe.client import (
    CheckoutSessionResult,
    InvoiceResult,
    PaymentMethodResult,
    SetupIntentResult,
    SubscriptionResult,
    get_stripe_client,
)

# ===================
# Mock Stripe Client
# ===================


class MockStripeClient:
    """Canonical in-memory Stripe double.

    Its surface is spec-checked against the real ``StripeClient`` in
    test_mock_stripe_contract.py (method set, signatures, asyncness), so it
    cannot drift the way per-file copies did.
    """

    def __init__(self) -> None:
        self.customers: dict[str, Customer] = {}
        self.customers_by_tenant: dict[str, str] = {}
        self.subscriptions: dict[str, dict[str, object]] = {}
        self.payment_methods: dict[str, dict[str, object]] = {}
        self.setup_intents: list[str] = []
        self.default_payment_methods: dict[str, str] = {}
        self.detached: list[str] = []
        self.reactivated: list[str] = []
        self.cancel_calls: list[tuple[str, bool]] = []
        self.update_calls: list[tuple[str, str]] = []
        self.checkout_sessions: list[tuple[str, str, str, str, int]] = []
        self.portal_sessions: list[tuple[str, str]] = []

    # Customer Management

    async def get_or_create_customer(
        self, tenant_id: str, email: str, name: str | None = None
    ) -> str:
        existing = self.customers_by_tenant.get(tenant_id)
        if existing is not None:
            return existing
        customer_id = f"cus_test_{len(self.customers)}"
        self.customers_by_tenant[tenant_id] = customer_id
        self.customers[customer_id] = Customer.construct_from(
            {
                "id": customer_id,
                "object": "customer",
                "email": email,
                "name": name or "",
                "metadata": {"tenant_id": tenant_id},
            },
            "sk_test",
        )
        return customer_id

    async def get_customer(self, customer_id: str) -> Customer | None:
        return self.customers.get(customer_id)

    # Payment Methods

    async def create_setup_intent(self, customer_id: str) -> SetupIntentResult:
        intent_id = f"seti_test_{len(self.setup_intents)}"
        self.setup_intents.append(intent_id)
        return SetupIntentResult(
            client_secret=f"{intent_id}_secret_test",
            customer_id=customer_id,
        )

    # Checkout & Portal

    async def create_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = 0,
    ) -> CheckoutSessionResult:
        session_id = f"cs_test_{len(self.checkout_sessions)}"
        self.checkout_sessions.append((customer_id, price_id, success_url, cancel_url, trial_days))
        return CheckoutSessionResult(
            url=f"https://checkout.stripe.com/c/pay/{session_id}",
            session_id=session_id,
        )

    async def create_portal_session(self, customer_id: str, return_url: str) -> str:
        self.portal_sessions.append((customer_id, return_url))
        return f"https://billing.stripe.com/p/session/{customer_id}"

    async def attach_payment_method(
        self, customer_id: str, payment_method_id: str
    ) -> PaymentMethodResult:
        pm = self.payment_methods.setdefault(payment_method_id, {})
        pm["customer"] = customer_id
        return PaymentMethodResult(
            id=payment_method_id,
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        self.detached.append(payment_method_id)
        self.payment_methods.pop(payment_method_id, None)
        return True

    async def list_payment_methods(self, customer_id: str) -> list[PaymentMethodResult]:
        return [
            PaymentMethodResult(
                id=pm_id,
                type="card",
                card_brand="visa",
                card_last4="4242",
                card_exp_month=12,
                card_exp_year=2030,
            )
            for pm_id, pm in self.payment_methods.items()
            if pm.get("customer") == customer_id
        ]

    async def set_default_payment_method(self, customer_id: str, payment_method_id: str) -> bool:
        self.default_payment_methods[customer_id] = payment_method_id
        return True

    async def get_default_payment_method(self, customer_id: str) -> str | None:
        return self.default_payment_methods.get(customer_id)

    # Subscriptions

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str,
        trial_days: int = 0,
    ) -> SubscriptionResult:
        sub_id = f"sub_test_{len(self.subscriptions)}"
        now = datetime.now(UTC)
        status = "trialing" if trial_days > 0 else "active"
        trial_start = now if trial_days > 0 else None
        trial_end = now + timedelta(days=trial_days) if trial_days > 0 else None
        self.subscriptions[sub_id] = {
            "customer": customer_id,
            "price_id": price_id,
            "status": status,
            "cancel_at_period_end": False,
        }
        return SubscriptionResult(
            id=sub_id,
            status=status,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
            trial_start=trial_start,
            trial_end=trial_end,
        )

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str,
        proration_behavior: Literal[
            "always_invoice", "create_prorations", "none"
        ] = "create_prorations",
    ) -> SubscriptionResult:
        self.update_calls.append((subscription_id, price_id))
        sub = self.subscriptions.setdefault(subscription_id, {"status": "active"})
        sub["price_id"] = price_id
        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status=str(sub.get("status", "active")),
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        self.cancel_calls.append((subscription_id, at_period_end))
        sub = self.subscriptions.get(subscription_id)
        if sub is not None:
            if at_period_end:
                sub["cancel_at_period_end"] = True
            else:
                sub["status"] = "canceled"
        return True

    async def reactivate_subscription(self, subscription_id: str) -> SubscriptionResult:
        self.reactivated.append(subscription_id)
        sub = self.subscriptions.setdefault(subscription_id, {"status": "active"})
        sub["cancel_at_period_end"] = False
        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def get_subscription(self, subscription_id: str) -> SubscriptionResult | None:
        sub = self.subscriptions.get(subscription_id)
        if sub is None:
            return None
        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status=str(sub.get("status", "active")),
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=bool(sub.get("cancel_at_period_end", False)),
        )

    # Invoices

    async def list_invoices(self, customer_id: str, limit: int = 10) -> list[InvoiceResult]:
        now = datetime.now(UTC)
        return [
            InvoiceResult(
                id="in_test_1",
                amount_due=2900,
                amount_paid=2900,
                currency="usd",
                status="paid",
                period_start=now - timedelta(days=30),
                period_end=now,
                paid_at=now - timedelta(days=29),
            )
        ]

    # Webhooks

    def verify_webhook_signature(
        self, payload: bytes, sig_header: str, webhook_secret: str
    ) -> Event:
        return Event.construct_from(json.loads(payload), "sk_test")


# ===================
# Stripe webhook payload builders (stripe-python 15 / dahlia shapes)
# ===================


def sign_stripe_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a real Stripe-Signature header for the payload."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def make_stripe_subscription(**overrides: object) -> StripeSubscription:
    """Typed Stripe Subscription payload: billing periods live on the items."""
    data: dict[str, object] = {
        "id": "sub_123",
        "object": "subscription",
        "status": "active",
        "cancel_at_period_end": False,
        "canceled_at": None,
        "trial_start": None,
        "trial_end": None,
        "items": {
            "object": "list",
            "data": [
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                }
            ],
            "has_more": False,
        },
    }
    data.update(overrides)
    return StripeSubscription.construct_from(data, "sk_test")


def make_stripe_invoice(subscription: str | None = "sub_123", **overrides: object) -> StripeInvoice:
    """Typed Stripe Invoice payload: the owning subscription rides under ``parent``."""
    parent: dict[str, object] | None = None
    if subscription is not None:
        parent = {
            "type": "subscription_details",
            "subscription_details": {
                "subscription": subscription,
                "metadata": {},
                "subscription_proration_date": None,
            },
            "quote_details": None,
        }
    data: dict[str, object] = {
        "id": "in_123",
        "object": "invoice",
        "number": "INV-001",
        "amount_due": 2900,
        "amount_paid": 2900,
        "currency": "usd",
        "period_start": 1700000000,
        "period_end": 1702592000,
        "hosted_invoice_url": None,
        "invoice_pdf": None,
        "parent": parent,
    }
    data.update(overrides)
    return StripeInvoice.construct_from(data, "sk_test")


def make_stripe_payment_method(**overrides: object) -> StripePaymentMethod:
    """Typed Stripe PaymentMethod payload."""
    data: dict[str, object] = {
        "id": "pm_123",
        "object": "payment_method",
        "type": "card",
        "customer": "cus_123",
        "card": {
            "brand": "visa",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2030,
        },
    }
    data.update(overrides)
    return StripePaymentMethod.construct_from(data, "sk_test")


# ===================
# Mock database models
# ===================


class MockPlan:
    """Mock Plan object for testing."""

    def __init__(
        self,
        id: UUID | None = None,
        name: str = "starter",
        display_name: str = "Starter",
        tier: int = billing_pb2.PLAN_TIER_STARTER,
        price_monthly: Decimal = Decimal("29"),
        price_yearly: Decimal = Decimal("290"),
        features: Mapping[str, object] | None = None,
        limits: Mapping[str, object] | None = None,
        trial_days: int = 14,
        stripe_price_id_monthly: str = "price_monthly_test",
        stripe_price_id_yearly: str = "price_yearly_test",
        is_active: bool = True,
        sort_order: int = 1,
        description: str | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.name = name
        self.display_name = display_name
        self.description = description
        self.tier = tier
        self.price_monthly = price_monthly
        self.price_yearly = price_yearly
        self.features: dict[str, object] = dict(features or {"backtests": True})
        self.limits: dict[str, object] = dict(limits or {"backtests_per_month": 50})
        self.trial_days = trial_days
        self.stripe_price_id_monthly = stripe_price_id_monthly
        self.stripe_price_id_yearly = stripe_price_id_yearly
        self.is_active = is_active
        self.sort_order = sort_order


class MockSubscription:
    """Mock Subscription object for testing."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        plan: MockPlan | None = None,
        status: int = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        billing_cycle: int = billing_pb2.BILLING_INTERVAL_MONTHLY,
        stripe_subscription_id: str | None = "sub_test_123",
        stripe_customer_id: str | None = "cus_test_123",
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
        trial_start: datetime | None = None,
        trial_end: datetime | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.plan = plan or MockPlan()
        self.plan_id = self.plan.id
        self.status = status
        self.billing_cycle = billing_cycle
        self.stripe_subscription_id = stripe_subscription_id
        self.stripe_customer_id = stripe_customer_id
        now = datetime.now(UTC)
        self.current_period_start = current_period_start or now
        self.current_period_end = current_period_end or (now + timedelta(days=30))
        self.cancel_at_period_end = cancel_at_period_end
        self.trial_start = trial_start
        self.trial_end = trial_end
        self.created_at = created_at or now
        self.canceled_at: datetime | None = None


# ===================
# Mock database session
# ===================


class _MockScalars:
    """Scalars facade over the routed rows."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def first(self) -> object | None:
        return self._rows[0] if self._rows else None


class _MockResult:
    """Result facade over the rows of the statement's target table."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _MockScalars:
        return _MockScalars(self._rows)

    def scalar_one_or_none(self) -> object | None:
        return self._rows[0] if self._rows else None

    def scalar(self) -> object | None:
        return self._rows[0] if self._rows else None


class MockAsyncSession:
    """Statement-aware async session double.

    Each statement is answered from the in-memory rows of the table it
    targets, so handlers issuing several different queries see honest
    per-table results instead of call-order plumbing; ``add`` files the
    object under its model's table.
    """

    _TABLES = ("payment_methods", "subscriptions", "invoices", "plans")

    def __init__(self) -> None:
        self.plans: list[object] = []
        self.subscriptions: list[object] = []
        self.payment_methods: list[object] = []
        self.invoices: list[object] = []
        self.added: list[object] = []
        self.commit_count = 0

    def _rows_for(self, table: str) -> list[object] | None:
        buckets: dict[str, list[object]] = {
            "plans": self.plans,
            "subscriptions": self.subscriptions,
            "payment_methods": self.payment_methods,
            "invoices": self.invoices,
        }
        return buckets.get(table)

    def _route(self, sql: str) -> list[object]:
        for table in self._TABLES:
            if table in sql:
                rows = self._rows_for(table)
                if rows is not None:
                    return rows
        return []

    async def execute(self, query: object) -> _MockResult:
        return _MockResult(list(self._route(str(query))))

    async def scalar(self, query: object) -> object | None:
        rows = self._route(str(query))
        return rows[0] if rows else None

    def add(self, obj: object) -> None:
        self.added.append(obj)
        table = str(getattr(type(obj), "__tablename__", ""))
        rows = self._rows_for(table)
        if rows is not None:
            rows.append(obj)

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: object, attrs: list[str] | None = None) -> None:
        return None

    async def rollback(self) -> None:
        return None


# ===================
# Real-SQL-on-SQLite tier
# ===================

_SQLITE_TIER_PATH = (
    Path(__file__).resolve().parents[3] / "libs" / "db" / "tests" / "_sqlite_tier.py"
)


def _load_sqlite_tier() -> None:
    """Load the shared tier module for its JSONB-on-SQLite rendering hook."""
    spec = spec_from_file_location("llamatrade_db_tests_sqlite_tier", _SQLITE_TIER_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)


_load_sqlite_tier()


@compiles(PG_UUID, "sqlite")
def _render_uuid_on_sqlite(
    type_: PG_UUID[UUID], compiler: GenericTypeCompiler, **kw: object
) -> str:
    """SQLite has no UUID type; CHAR(32) keeps hex text out of NUMERIC affinity."""
    return "CHAR(32)"


def _awaken_utc(instance: object) -> None:
    """Give naive datetimes loaded from SQLite the UTC awareness Postgres provides."""
    state = vars(instance)
    for key, value in list(state.items()):
        if isinstance(value, datetime) and value.tzinfo is None:
            state[key] = value.replace(tzinfo=UTC)


@event.listens_for(Session, "loaded_as_persistent")
def _utc_on_load(session: Session, instance: object) -> None:
    _awaken_utc(instance)


@event.listens_for(Base, "refresh", propagate=True)
def _utc_on_refresh(instance: object, context: object, attrs: object) -> None:
    _awaken_utc(instance)


class SqliteSessionAdapter:
    """Async facade over a sync Session for driving the servicer on SQLite.

    Extends the shared real-SQL-on-SQLite tier (libs/db/tests/_sqlite_tier.py,
    loaded above for its JSONB rendering) with the surface ``tenant_session``
    and the billing services need: context management, writes, and a no-op for
    the Postgres-only RLS ``set_config`` statement.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    async def __aenter__(self) -> SqliteSessionAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._session.close()

    async def execute(
        self, statement: Executable, params: dict[str, object] | None = None
    ) -> Result[tuple[object, ...]]:
        if isinstance(statement, TextClause) and "set_config" in statement.text:
            return self._session.execute(text("SELECT 1"))
        return self._session.execute(statement, params)

    async def scalar(self, statement: Executable) -> object | None:
        return self._session.scalar(statement)

    def add(self, obj: object) -> None:
        self._session.add(obj)

    async def delete(self, obj: object) -> None:
        self._session.delete(obj)

    async def flush(self) -> None:
        self._session.flush()

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, obj: object, attribute_names: list[str] | None = None) -> None:
        self._session.refresh(obj, attribute_names)

    async def close(self) -> None:
        self._session.close()


_SQLITE_TABLES = [
    Plan.__table__,
    Subscription.__table__,
    PaymentMethod.__table__,
    Invoice.__table__,
]


@pytest.fixture
def sqlite_sessions() -> Iterator[sessionmaker[Session]]:
    """Session factory over a fresh in-memory SQLite schema (billing tables only)."""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine, tables=_SQLITE_TABLES)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    engine.dispose()


@pytest.fixture
def sqlite_servicer(sqlite_sessions: sessionmaker[Session]) -> BillingServicer:
    """BillingServicer whose tenant sessions run real SQL on SQLite."""
    servicer = BillingServicer()
    servicer._session_maker = cast(
        "async_sessionmaker[AsyncSession]",
        lambda: SqliteSessionAdapter(sqlite_sessions()),
    )
    return servicer


def seed_plan(
    session: Session,
    *,
    name: str = "starter",
    stripe_price_id_monthly: str | None = "price_monthly_test",
    stripe_price_id_yearly: str | None = "price_yearly_test",
) -> Plan:
    """Insert (flush) a plan row; committed with the first seeded child row."""
    plan = Plan(
        name=name,
        display_name=name.capitalize(),
        tier=billing_pb2.PLAN_TIER_STARTER,
        price_monthly=Decimal("29"),
        price_yearly=Decimal("290"),
        features={"backtests": True},
        limits={"backtests_per_month": 50, "live_strategies": 1},
        trial_days=14,
        stripe_price_id_monthly=stripe_price_id_monthly,
        stripe_price_id_yearly=stripe_price_id_yearly,
        is_active=True,
        sort_order=1,
    )
    session.add(plan)
    session.flush()
    return plan


def seed_subscription(
    session: Session,
    *,
    tenant_id: UUID,
    plan: Plan,
    status: billing_pb2.SubscriptionStatus.ValueType = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
    cancel_at_period_end: bool = False,
    stripe_subscription_id: str | None = "sub_seeded_1",
    stripe_customer_id: str | None = "cus_seeded_1",
) -> Subscription:
    """Insert and commit a subscription row for ``tenant_id``."""
    now = datetime.now(UTC)
    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        status=status,
        billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=cancel_at_period_end,
    )
    session.add(subscription)
    session.commit()
    return subscription


def seed_payment_method(
    session: Session,
    *,
    tenant_id: UUID,
    stripe_payment_method_id: str,
    is_default: bool = False,
    card_last4: str = "4242",
    created_at: datetime | None = None,
) -> PaymentMethod:
    """Insert and commit a payment-method row for ``tenant_id``."""
    payment_method = PaymentMethod(
        tenant_id=tenant_id,
        stripe_payment_method_id=stripe_payment_method_id,
        stripe_customer_id="cus_seeded_1",
        type="card",
        card_brand="visa",
        card_last4=card_last4,
        card_exp_month=12,
        card_exp_year=2030,
        is_default=is_default,
    )
    if created_at is not None:
        payment_method.created_at = created_at
        payment_method.updated_at = created_at
    session.add(payment_method)
    session.commit()
    return payment_method


def seed_invoice(
    session: Session, *, tenant_id: UUID, stripe_invoice_id: str | None = None
) -> Invoice:
    """Insert and commit a paid invoice row for ``tenant_id``."""
    now = datetime.now(UTC)
    invoice = Invoice(
        tenant_id=tenant_id,
        stripe_invoice_id=stripe_invoice_id or f"in_seed_{uuid4().hex[:8]}",
        status=billing_pb2.INVOICE_STATUS_PAID,
        amount_due=Decimal("29.00"),
        amount_paid=Decimal("29.00"),
        currency="usd",
        period_start=now - timedelta(days=30),
        period_end=now,
    )
    session.add(invoice)
    session.commit()
    return invoice


# ===================
# Fixtures
# ===================


@pytest.fixture
def mock_stripe_client() -> MockStripeClient:
    """Create a mock Stripe client."""
    return MockStripeClient()


@pytest.fixture
def mock_db() -> MockAsyncSession:
    """Create a mock database session."""
    return MockAsyncSession()


@pytest.fixture
async def client(
    mock_stripe_client: MockStripeClient, mock_db: MockAsyncSession
) -> AsyncGenerator[AsyncClient]:
    """Create async test client with mocked dependencies."""

    async def get_mock_db() -> AsyncGenerator[MockAsyncSession]:
        yield mock_db

    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    app.dependency_overrides[get_db] = get_mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fake_notification_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the shared notification publisher at an in-memory stream."""
    from llamatrade_events import EventBus
    from llamatrade_events.catalog import notifications as notifications_module
    from llamatrade_events.catalog.notifications import NotificationEvents
    from llamatrade_events.testing import FakeTransport

    monkeypatch.setattr(
        notifications_module,
        "_shared",
        NotificationEvents(bus=EventBus(FakeTransport())),
    )
