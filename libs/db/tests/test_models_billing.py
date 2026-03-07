"""Tests for llamatrade_db.models.billing module."""

from llamatrade_db.models.billing import (
    Invoice,
    PaymentMethod,
    Plan,
    Subscription,
    UsageRecord,
)


class TestPlan:
    """Tests for Plan model."""

    def test_plan_tablename(self) -> None:
        """Test Plan has correct tablename."""
        assert Plan.__tablename__ == "plans"

    def test_plan_has_required_columns(self) -> None:
        """Test Plan has all required columns."""
        columns = Plan.__table__.columns
        assert "id" in columns
        assert "name" in columns
        assert "display_name" in columns
        assert "description" in columns
        assert "tier" in columns
        assert "price_monthly" in columns
        assert "price_yearly" in columns
        assert "stripe_price_id_monthly" in columns
        assert "stripe_price_id_yearly" in columns
        assert "features" in columns
        assert "limits" in columns
        assert "trial_days" in columns
        assert "is_active" in columns
        assert "sort_order" in columns

    def test_plan_name_unique(self) -> None:
        """Test name column is unique."""
        col = Plan.__table__.columns["name"]
        assert col.unique is True

    def test_plan_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = Plan.__table__.columns["name"]
        assert col.nullable is False

    def test_plan_price_monthly_not_nullable(self) -> None:
        """Test price_monthly is not nullable."""
        col = Plan.__table__.columns["price_monthly"]
        assert col.nullable is False

    def test_plan_has_subscriptions_relationship(self) -> None:
        """Test Plan has subscriptions relationship."""
        assert hasattr(Plan, "subscriptions")


class TestSubscription:
    """Tests for Subscription model."""

    def test_subscription_tablename(self) -> None:
        """Test Subscription has correct tablename."""
        assert Subscription.__tablename__ == "subscriptions"

    def test_subscription_has_required_columns(self) -> None:
        """Test Subscription has all required columns."""
        columns = Subscription.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "plan_id" in columns
        assert "status" in columns
        assert "billing_cycle" in columns
        assert "stripe_subscription_id" in columns
        assert "stripe_customer_id" in columns
        assert "current_period_start" in columns
        assert "current_period_end" in columns
        assert "canceled_at" in columns
        assert "cancel_at_period_end" in columns
        assert "trial_start" in columns
        assert "trial_end" in columns

    def test_subscription_status_not_nullable(self) -> None:
        """Test status column is not nullable."""
        col = Subscription.__table__.columns["status"]
        assert col.nullable is False

    def test_subscription_billing_cycle_not_nullable(self) -> None:
        """Test billing_cycle column is not nullable."""
        col = Subscription.__table__.columns["billing_cycle"]
        assert col.nullable is False

    def test_subscription_has_plan_relationship(self) -> None:
        """Test Subscription has plan relationship."""
        assert hasattr(Subscription, "plan")


class TestUsageRecord:
    """Tests for UsageRecord model."""

    def test_usage_record_tablename(self) -> None:
        """Test UsageRecord has correct tablename."""
        assert UsageRecord.__tablename__ == "usage_records"

    def test_usage_record_has_required_columns(self) -> None:
        """Test UsageRecord has all required columns."""
        columns = UsageRecord.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "subscription_id" in columns
        assert "metric_name" in columns
        assert "quantity" in columns
        assert "period_start" in columns
        assert "period_end" in columns
        assert "reported_to_stripe" in columns
        assert "stripe_usage_record_id" in columns

    def test_usage_record_metric_name_not_nullable(self) -> None:
        """Test metric_name column is not nullable."""
        col = UsageRecord.__table__.columns["metric_name"]
        assert col.nullable is False

    def test_usage_record_quantity_not_nullable(self) -> None:
        """Test quantity column is not nullable."""
        col = UsageRecord.__table__.columns["quantity"]
        assert col.nullable is False


class TestInvoice:
    """Tests for Invoice model."""

    def test_invoice_tablename(self) -> None:
        """Test Invoice has correct tablename."""
        assert Invoice.__tablename__ == "invoices"

    def test_invoice_has_required_columns(self) -> None:
        """Test Invoice has all required columns."""
        columns = Invoice.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "subscription_id" in columns
        assert "stripe_invoice_id" in columns
        assert "invoice_number" in columns
        assert "status" in columns
        assert "amount_due" in columns
        assert "amount_paid" in columns
        assert "currency" in columns
        assert "period_start" in columns
        assert "period_end" in columns
        assert "due_date" in columns
        assert "paid_at" in columns
        assert "hosted_invoice_url" in columns
        assert "invoice_pdf" in columns
        assert "line_items" in columns

    def test_invoice_stripe_invoice_id_unique(self) -> None:
        """Test stripe_invoice_id is unique."""
        col = Invoice.__table__.columns["stripe_invoice_id"]
        assert col.unique is True

    def test_invoice_status_not_nullable(self) -> None:
        """Test status column is not nullable."""
        col = Invoice.__table__.columns["status"]
        assert col.nullable is False


class TestPaymentMethod:
    """Tests for PaymentMethod model."""

    def test_payment_method_tablename(self) -> None:
        """Test PaymentMethod has correct tablename."""
        assert PaymentMethod.__tablename__ == "payment_methods"

    def test_payment_method_has_required_columns(self) -> None:
        """Test PaymentMethod has all required columns."""
        columns = PaymentMethod.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "stripe_payment_method_id" in columns
        assert "stripe_customer_id" in columns
        assert "type" in columns
        assert "card_brand" in columns
        assert "card_last4" in columns
        assert "card_exp_month" in columns
        assert "card_exp_year" in columns
        assert "is_default" in columns

    def test_payment_method_stripe_pm_id_unique(self) -> None:
        """Test stripe_payment_method_id is unique."""
        col = PaymentMethod.__table__.columns["stripe_payment_method_id"]
        assert col.unique is True

    def test_payment_method_type_not_nullable(self) -> None:
        """Test type column is not nullable."""
        col = PaymentMethod.__table__.columns["type"]
        assert col.nullable is False
