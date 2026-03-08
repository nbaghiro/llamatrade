"""Billing and subscription models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

See libs/db/llamatrade_db/models/enum_types.py for TypeDecorator implementations.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    BillingIntervalType,
    InvoiceStatusType,
    PlanTierType,
    SubscriptionStatusType,
)
from llamatrade_proto.generated import billing_pb2


class Plan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Subscription plan definition (not tenant-scoped)."""

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[billing_pb2.PlanTier.ValueType] = mapped_column(PlanTierType(), nullable=False)
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)
    price_yearly: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )
    stripe_price_id_monthly: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_price_id_yearly: Mapped[str | None] = mapped_column(String(100), nullable=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="plan")


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
    status: Mapped[billing_pb2.SubscriptionStatus.ValueType] = mapped_column(
        SubscriptionStatusType(), nullable=False
    )
    billing_cycle: Mapped[billing_pb2.BillingInterval.ValueType] = mapped_column(
        BillingIntervalType(), nullable=False
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    plan: Mapped[Plan] = relationship("Plan", back_populates="subscriptions")


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
    status: Mapped[int] = mapped_column(InvoiceStatusType(), nullable=False)
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
    line_items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)


class PaymentMethod(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Saved payment method (synced from Stripe)."""

    __tablename__ = "payment_methods"
    __table_args__ = (
        Index("ix_payment_methods_stripe_pm", "stripe_payment_method_id"),
        Index("ix_payment_methods_stripe_customer", "stripe_customer_id"),
    )

    stripe_payment_method_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # card, bank_account
    card_brand: Mapped[str | None] = mapped_column(String(50), nullable=True)  # visa, mastercard
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
