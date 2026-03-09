"""Test data factories for integration tests.

These factories create database model instances with sensible defaults.
Use them to quickly create test data without specifying every field.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from llamatrade_db.models import (
    Backtest,
    BacktestResult,
    Invoice,
    Order,
    PaymentMethod,
    Plan,
    Position,
    Strategy,
    StrategyVersion,
    Subscription,
    Tenant,
    TradingSession,
    User,
)

# Backtest enums (re-exported for tests)
from llamatrade_proto.generated.backtest_pb2 import (  # noqa: F401
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)

# Billing enums (re-exported for tests)
from llamatrade_proto.generated.billing_pb2 import (  # noqa: F401
    BILLING_INTERVAL_MONTHLY,
    PLAN_TIER_STARTER,
    SUBSCRIPTION_STATUS_ACTIVE,
)

# Common enums (re-exported for tests)
from llamatrade_proto.generated.common_pb2 import (  # noqa: F401
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)

# Strategy enums (re-exported for tests)
from llamatrade_proto.generated.strategy_pb2 import (  # noqa: F401
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    STRATEGY_STATUS_DRAFT,
)

# Trading enums (re-exported for tests)
from llamatrade_proto.generated.trading_pb2 import (  # noqa: F401
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_PENDING,
    ORDER_TYPE_MARKET,
    POSITION_SIDE_LONG,
    TIME_IN_FORCE_DAY,
)

# Aliases for SESSION_STATUS (mapped to EXECUTION_STATUS in proto)
SESSION_STATUS_ACTIVE = EXECUTION_STATUS_RUNNING
SESSION_STATUS_PAUSED = EXECUTION_STATUS_PAUSED
SESSION_STATUS_STOPPED = EXECUTION_STATUS_STOPPED
SESSION_STATUS_ERROR = EXECUTION_STATUS_ERROR

# DB-only enums (not in proto)
# InvoiceStatus: DRAFT=1, OPEN=2, PAID=3, VOID=4, UNCOLLECTIBLE=5
INVOICE_STATUS_DRAFT = 1
INVOICE_STATUS_OPEN = 2
INVOICE_STATUS_PAID = 3
INVOICE_STATUS_VOID = 4
INVOICE_STATUS_UNCOLLECTIBLE = 5


class TenantFactory:
    """Factory for creating Tenant instances."""

    @staticmethod
    def create(
        *,
        id: UUID | None = None,
        name: str = "Test Organization",
        slug: str | None = None,
        is_active: bool = True,
        settings: dict | None = None,
    ) -> Tenant:
        """Create a Tenant instance with defaults."""
        return Tenant(
            id=id or uuid4(),
            name=name,
            slug=slug or f"test-org-{uuid4().hex[:8]}",
            is_active=is_active,
            settings=settings or {"timezone": "UTC"},
        )


class UserFactory:
    """Factory for creating User instances."""

    # bcrypt hash for "password123"
    DEFAULT_PASSWORD_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.s1X5GmXBiLNjNW"

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        id: UUID | None = None,
        email: str | None = None,
        password_hash: str | None = None,
        first_name: str = "Test",
        last_name: str = "User",
        role: str = "user",
        is_active: bool = True,
        is_verified: bool = True,
    ) -> User:
        """Create a User instance with defaults."""
        return User(
            id=id or uuid4(),
            tenant_id=tenant_id,
            email=email or f"user-{uuid4().hex[:8]}@example.com",
            password_hash=password_hash or UserFactory.DEFAULT_PASSWORD_HASH,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active,
            is_verified=is_verified,
        )


class StrategyFactory:
    """Factory for creating Strategy instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        created_by: UUID,
        id: UUID | None = None,
        name: str = "Test Strategy",
        description: str | None = "A test trading strategy",
        status: int = STRATEGY_STATUS_DRAFT,  # Proto int: DRAFT=1
        is_public: bool = False,
        current_version: int = 1,
    ) -> Strategy:
        """Create a Strategy instance with defaults."""
        return Strategy(
            id=id or uuid4(),
            tenant_id=tenant_id,
            created_by=created_by,
            name=name,
            description=description,
            status=status,
            is_public=is_public,
            current_version=current_version,
        )


class StrategyVersionFactory:
    """Factory for creating StrategyVersion instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        strategy_id: UUID,
        created_by: UUID,
        id: UUID | None = None,
        version: int = 1,
        config_sexpr: str | None = None,
        config_json: dict | None = None,
        symbols: list[str] | None = None,
        timeframe: str = "1D",
        changelog: str | None = "Initial version",
    ) -> StrategyVersion:
        """Create a StrategyVersion instance with defaults."""
        default_config_sexpr = """
(strategy
  (name "Test Strategy")
  (symbols ["AAPL"])
  (timeframe "1D")
  (conditions
    (cross_above close sma_20))
  (actions
    (buy 10%)))
"""
        default_config_json = {
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "indicators": [],
            "conditions": [{"type": "cross_above", "left": "close", "right": "sma_20"}],
            "actions": [{"type": "buy", "quantity_type": "percent", "quantity_value": 10}],
        }

        return StrategyVersion(
            id=id or uuid4(),
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            version=version,
            config_sexpr=config_sexpr or default_config_sexpr,
            config_json=config_json or default_config_json,
            symbols=symbols or ["AAPL"],
            timeframe=timeframe,
            changelog=changelog,
            created_by=created_by,
        )


class BacktestFactory:
    """Factory for creating Backtest instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        strategy_id: UUID,
        created_by: UUID,
        id: UUID | None = None,
        name: str = "Test Backtest",
        strategy_version: int = 1,
        status: int = BACKTEST_STATUS_PENDING,  # Proto int: PENDING=1
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        initial_capital: Decimal = Decimal("100000.00"),
        symbols: list[str] | None = None,
        config: dict | None = None,
    ) -> Backtest:
        """Create a Backtest instance with defaults."""
        now = datetime.now(UTC)

        return Backtest(
            id=id or uuid4(),
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            name=name,
            status=status,
            start_date=start_date or (now - timedelta(days=365)).date(),
            end_date=end_date or now.date(),
            initial_capital=initial_capital,
            symbols=symbols or ["AAPL"],
            config=config or {},
            created_by=created_by,
        )


class BacktestResultFactory:
    """Factory for creating BacktestResult instances."""

    @staticmethod
    def create(
        *,
        backtest_id: UUID,
        id: UUID | None = None,
        total_return: Decimal = Decimal("0.150000"),
        annual_return: Decimal = Decimal("0.120000"),
        sharpe_ratio: Decimal = Decimal("1.5000"),
        sortino_ratio: Decimal | None = Decimal("2.0000"),
        max_drawdown: Decimal = Decimal("-0.080000"),
        max_drawdown_duration: int | None = 30,
        win_rate: Decimal = Decimal("0.5500"),
        profit_factor: Decimal | None = Decimal("1.8000"),
        exposure_time: Decimal | None = Decimal("75.00"),
        total_trades: int = 50,
        winning_trades: int = 27,
        losing_trades: int = 23,
        avg_trade_return: Decimal = Decimal("0.003000"),
        final_equity: Decimal = Decimal("115000.00"),
        equity_curve: list | None = None,
        trades: list | None = None,
        daily_returns: list | None = None,
        monthly_returns: dict | None = None,
    ) -> BacktestResult:
        """Create a BacktestResult instance with defaults."""
        return BacktestResult(
            id=id or uuid4(),
            backtest_id=backtest_id,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_drawdown_duration,
            win_rate=win_rate,
            profit_factor=profit_factor,
            exposure_time=exposure_time,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_return=avg_trade_return,
            final_equity=final_equity,
            equity_curve=equity_curve or [],
            trades=trades or [],
            daily_returns=daily_returns or [],
            monthly_returns=monthly_returns or {},
        )


class TradingSessionFactory:
    """Factory for creating TradingSession instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        strategy_id: UUID,
        credentials_id: UUID,
        created_by: UUID,
        id: UUID | None = None,
        name: str = "Test Session",
        strategy_version: int = 1,
        status: int = SESSION_STATUS_STOPPED,  # Proto int: STOPPED=3
        mode: int = EXECUTION_MODE_PAPER,  # Proto int: PAPER=1
        config: dict | None = None,
        symbols: list | None = None,
    ) -> TradingSession:
        """Create a TradingSession instance with defaults."""
        return TradingSession(
            id=id or uuid4(),
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            credentials_id=credentials_id,
            name=name,
            status=status,
            mode=mode,
            config=config or {},
            symbols=symbols or ["AAPL"],
            created_by=created_by,
        )


class OrderFactory:
    """Factory for creating Order instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        session_id: UUID,
        id: UUID | None = None,
        client_order_id: str | None = None,
        symbol: str = "AAPL",
        side: int = ORDER_SIDE_BUY,  # Proto int: BUY=1
        qty: Decimal = Decimal("10.00000000"),
        order_type: int = ORDER_TYPE_MARKET,  # Proto int: MARKET=1
        time_in_force: int = TIME_IN_FORCE_DAY,  # Proto int: DAY=1
        status: int = ORDER_STATUS_PENDING,  # Proto int: PENDING=1
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        filled_qty: Decimal = Decimal("0"),
        filled_avg_price: Decimal | None = None,
        alpaca_order_id: str | None = None,
    ) -> Order:
        """Create an Order instance with defaults."""
        return Order(
            id=id or uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            client_order_id=client_order_id or f"order-{uuid4().hex[:12]}",
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            time_in_force=time_in_force,
            status=status,
            limit_price=limit_price,
            stop_price=stop_price,
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
            alpaca_order_id=alpaca_order_id,
        )


class PositionFactory:
    """Factory for creating Position instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        session_id: UUID,
        id: UUID | None = None,
        symbol: str = "AAPL",
        side: int = POSITION_SIDE_LONG,  # Proto int: LONG=1
        qty: Decimal = Decimal("10.00000000"),
        avg_entry_price: Decimal = Decimal("150.00000000"),
        current_price: Decimal | None = Decimal("155.00000000"),
        market_value: Decimal | None = None,
        cost_basis: Decimal | None = None,
        unrealized_pl: Decimal | None = None,
        unrealized_plpc: Decimal | None = None,
        realized_pl: Decimal = Decimal("0.00"),
        is_open: bool = True,
        opened_at: datetime | None = None,
    ) -> Position:
        """Create a Position instance with defaults."""
        if market_value is None and current_price:
            market_value = qty * current_price
        if cost_basis is None:
            cost_basis = qty * avg_entry_price
        if unrealized_pl is None and current_price:
            unrealized_pl = (current_price - avg_entry_price) * qty
        if opened_at is None:
            opened_at = datetime.now(UTC)

        return Position(
            id=id or uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            symbol=symbol,
            side=side,
            qty=qty,
            avg_entry_price=avg_entry_price,
            current_price=current_price,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pl=unrealized_pl,
            unrealized_plpc=unrealized_plpc,
            realized_pl=realized_pl,
            is_open=is_open,
            opened_at=opened_at,
        )


class PlanFactory:
    """Factory for creating Plan instances."""

    @staticmethod
    def create(
        *,
        id: UUID | None = None,
        name: str = "starter",
        display_name: str = "Starter",
        tier: int = PLAN_TIER_STARTER,  # Proto int: FREE=1, STARTER=2, PRO=3
        price_monthly: float = 29.0,
        price_yearly: float = 290.0,
        features: dict | None = None,
        limits: dict | None = None,
        trial_days: int = 14,
        stripe_price_id_monthly: str = "price_monthly_test",
        stripe_price_id_yearly: str = "price_yearly_test",
        is_active: bool = True,
        sort_order: int = 1,
    ) -> Plan:
        """Create a Plan instance with defaults."""
        return Plan(
            id=id or uuid4(),
            name=name,
            display_name=display_name,
            tier=tier,
            price_monthly=price_monthly,
            price_yearly=price_yearly,
            features=features or {"backtests": True, "paper_trading": True},
            limits=limits or {"backtests_per_month": 50, "live_strategies": 1},
            trial_days=trial_days,
            stripe_price_id_monthly=stripe_price_id_monthly,
            stripe_price_id_yearly=stripe_price_id_yearly,
            is_active=is_active,
            sort_order=sort_order,
        )


class SubscriptionFactory:
    """Factory for creating Subscription instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        plan_id: UUID,
        id: UUID | None = None,
        status: int = SUBSCRIPTION_STATUS_ACTIVE,  # Proto int: ACTIVE=1, PAST_DUE=2, etc.
        billing_cycle: int = BILLING_INTERVAL_MONTHLY,  # Proto int: MONTHLY=1, YEARLY=2
        stripe_subscription_id: str | None = "sub_test_123",
        stripe_customer_id: str | None = "cus_test_123",
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
    ) -> Subscription:
        """Create a Subscription instance with defaults."""
        now = datetime.now(UTC)

        return Subscription(
            id=id or uuid4(),
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            billing_cycle=billing_cycle,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            current_period_start=current_period_start or now,
            current_period_end=current_period_end or (now + timedelta(days=30)),
            cancel_at_period_end=cancel_at_period_end,
        )


class InvoiceFactory:
    """Factory for creating Invoice instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        stripe_invoice_id: str | None = None,
        id: UUID | None = None,
        invoice_number: str | None = None,
        status: int = INVOICE_STATUS_OPEN,  # DB-only: DRAFT=1, OPEN=2, PAID=3, VOID=4, UNCOLLECTIBLE=5
        amount_due: Decimal = Decimal("29.00"),
        amount_paid: Decimal = Decimal("0.00"),
        currency: str = "usd",
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        due_date: datetime | None = None,
        paid_at: datetime | None = None,
        hosted_invoice_url: str | None = None,
        invoice_pdf: str | None = None,
    ) -> Invoice:
        """Create an Invoice instance with defaults."""
        now = datetime.now(UTC)

        return Invoice(
            id=id or uuid4(),
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            stripe_invoice_id=stripe_invoice_id or f"in_{uuid4().hex[:24]}",
            invoice_number=invoice_number or f"INV-{uuid4().hex[:8].upper()}",
            status=status,
            amount_due=amount_due,
            amount_paid=amount_paid,
            currency=currency,
            period_start=period_start or now,
            period_end=period_end or (now + timedelta(days=30)),
            due_date=due_date,
            paid_at=paid_at,
            hosted_invoice_url=hosted_invoice_url,
            invoice_pdf=invoice_pdf,
        )


class PaymentMethodFactory:
    """Factory for creating PaymentMethod instances."""

    @staticmethod
    def create(
        *,
        tenant_id: UUID,
        stripe_customer_id: str,
        stripe_payment_method_id: str | None = None,
        id: UUID | None = None,
        type: str = "card",
        card_brand: str | None = "visa",
        card_last4: str | None = "4242",
        card_exp_month: int | None = 12,
        card_exp_year: int | None = 2030,
        is_default: bool = False,
    ) -> PaymentMethod:
        """Create a PaymentMethod instance with defaults."""
        return PaymentMethod(
            id=id or uuid4(),
            tenant_id=tenant_id,
            stripe_payment_method_id=stripe_payment_method_id or f"pm_{uuid4().hex[:24]}",
            stripe_customer_id=stripe_customer_id,
            type=type,
            card_brand=card_brand,
            card_last4=card_last4,
            card_exp_month=card_exp_month,
            card_exp_year=card_exp_year,
            is_default=is_default,
        )
