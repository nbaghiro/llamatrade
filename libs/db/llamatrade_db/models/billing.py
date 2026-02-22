"""Billing and subscription models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Plan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Subscription plan definition (not tenant-scoped)."""

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(String(50), nullable=False)  # free, starter, pro, enterprise
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)
    price_yearly: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )
    stripe_price_id_monthly: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_price_id_yearly: Mapped[str | None] = mapped_column(String(100), nullable=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="plan"
    )


class Subscription(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Tenant subscription to a plan."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        Index("ix_subscriptions_stripe", "stripe_subscription_id"),
    )

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # active, canceled, past_due, trialing, etc.
    billing_cycle: Mapped[str] = mapped_column(String(20), nullable=False)  # monthly, yearly
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", back_populates="subscriptions")


class UsageRecord(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Usage tracking for metered billing."""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_tenant_period", "tenant_id", "period_start", "period_end"),
        Index("ix_usage_records_metric", "metric_name"),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # api_calls, backtests, live_sessions, etc.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    reported_to_stripe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stripe_usage_record_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Invoice(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Invoice record (synced from Stripe)."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_stripe", "stripe_invoice_id"),
    )

    subscription_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True
    )
    stripe_invoice_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # draft, open, paid, void, uncollectible
    amount_due: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2), default=Decimal("0"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="usd", nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_pdf: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
