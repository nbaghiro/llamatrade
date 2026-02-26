"""Test risk manager."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models import RiskLimits
from src.risk.risk_manager import RiskManager, get_risk_manager


@pytest.fixture
def risk_manager():
    """Create a risk manager instance without DB."""
    return RiskManager()


@pytest.fixture
def risk_manager_with_db(mock_db):
    """Create a risk manager instance with mocked DB."""
    return RiskManager(db=mock_db)


class TestRiskManager:
    """Tests for RiskManager."""

    def test_default_limits(self, risk_manager):
        """Test default risk limits are set."""
        assert risk_manager._default_limits is not None
        assert risk_manager._default_limits.max_position_size == 10000
        assert risk_manager._default_limits.max_daily_loss == 1000
        assert risk_manager._default_limits.max_order_value == 5000

    async def test_get_limits_without_db(self, risk_manager, tenant_id):
        """Test getting limits without database returns defaults."""
        limits = await risk_manager.get_limits(tenant_id)

        assert limits is not None
        assert isinstance(limits, RiskLimits)
        assert limits.max_position_size == 10000

    async def test_get_limits_with_db_no_config(self, risk_manager_with_db, mock_db, tenant_id):
        """Test getting limits when no config exists in DB."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        limits = await risk_manager_with_db.get_limits(tenant_id)

        # Should return defaults
        assert limits.max_position_size == 10000

    async def test_check_order_passes(self, risk_manager, tenant_id):
        """Test order that passes risk checks."""
        result = await risk_manager.check_order(
            tenant_id=tenant_id,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
        )

        assert result.passed is True
        assert len(result.violations) == 0

    async def test_check_order_exceeds_value(self, risk_manager, tenant_id):
        """Test order that exceeds max order value."""
        # With default limit_price placeholder of 100 and max_order_value of 5000
        # qty of 100 * 100 = 10000 > 5000
        result = await risk_manager.check_order(
            tenant_id=tenant_id,
            symbol="AAPL",
            side="buy",
            qty=100.0,
            order_type="market",
        )

        assert result.passed is False
        assert len(result.violations) > 0
        assert any("exceeds limit" in v for v in result.violations)

    async def test_check_order_with_limit_price(self, risk_manager, tenant_id):
        """Test order value calculation with limit price."""
        # 20 shares * $300 = $6000 > $5000 max
        result = await risk_manager.check_order(
            tenant_id=tenant_id,
            symbol="GOOGL",
            side="buy",
            qty=20.0,
            order_type="limit",
            limit_price=300.0,
        )

        assert result.passed is False
        assert any("exceeds limit" in v for v in result.violations)

    async def test_check_order_allowed_symbols(self, risk_manager, tenant_id):
        """Test order with symbol restrictions."""
        # Override default limits with symbol restrictions
        risk_manager._default_limits = RiskLimits(
            max_order_value=10000,
            allowed_symbols=["AAPL", "GOOGL"],
        )

        # MSFT not in allowed list
        result = await risk_manager.check_order(
            tenant_id=tenant_id,
            symbol="MSFT",
            side="buy",
            qty=10.0,
            order_type="market",
        )

        assert result.passed is False
        assert any("not in allowed list" in v for v in result.violations)

    async def test_check_order_allowed_symbol(self, risk_manager, tenant_id):
        """Test order with allowed symbol."""
        risk_manager._default_limits = RiskLimits(
            max_order_value=10000,
            allowed_symbols=["AAPL", "GOOGL"],
        )

        result = await risk_manager.check_order(
            tenant_id=tenant_id,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
        )

        assert result.passed is True

    async def test_check_daily_loss_without_db(self, risk_manager, tenant_id):
        """Test daily loss check without DB returns True."""
        result = await risk_manager.check_daily_loss(tenant_id)

        assert result is True

    async def test_update_limits_without_db(self, risk_manager, tenant_id):
        """Test updating limits without DB."""
        new_limits = RiskLimits(
            max_position_size=20000,
            max_daily_loss=2000,
            max_order_value=10000,
        )

        result = await risk_manager.update_limits(tenant_id, new_limits)

        assert result.max_position_size == 20000
        assert result.max_daily_loss == 2000
        assert result.max_order_value == 10000

    async def test_get_current_drawdown_without_db(self, risk_manager, tenant_id, session_id):
        """Test getting drawdown without DB returns 0."""
        result = await risk_manager.get_current_drawdown(tenant_id, session_id)

        assert result == 0.0

    async def test_update_daily_pnl_without_db(self, risk_manager, tenant_id, session_id):
        """Test updating daily PnL without DB does nothing."""
        # Should not raise
        await risk_manager.update_daily_pnl(
            tenant_id=tenant_id,
            session_id=session_id,
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            equity=10150.0,
        )

    async def test_record_trade_without_db(self, risk_manager, tenant_id, session_id):
        """Test recording trade without DB does nothing."""
        # Should not raise
        await risk_manager.record_trade(
            tenant_id=tenant_id,
            session_id=session_id,
            is_win=True,
        )


class TestRiskManagerWithDB:
    """Tests for RiskManager with database."""

    async def test_check_rate_limit_under_limit(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test rate limit check when under limit."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5  # 5 orders in last minute
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._check_rate_limit(tenant_id, session_id)

        assert result is True

    async def test_check_rate_limit_over_limit(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test rate limit check when over limit."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15  # 15 orders in last minute
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._check_rate_limit(tenant_id, session_id)

        assert result is False

    async def test_get_daily_pnl(self, risk_manager_with_db, mock_db, tenant_id, session_id):
        """Test getting daily PnL from database."""
        mock_daily = MagicMock()
        mock_daily.total_pnl = -500.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._get_daily_pnl(tenant_id, session_id)

        assert result == -500.0

    async def test_get_daily_pnl_no_record(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test getting daily PnL when no record exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._get_daily_pnl(tenant_id, session_id)

        assert result == 0.0


class TestGetRiskManager:
    """Tests for get_risk_manager singleton."""

    def test_returns_manager(self):
        """Test that get_risk_manager returns a RiskManager."""
        manager = get_risk_manager()

        assert isinstance(manager, RiskManager)

    def test_returns_same_instance(self):
        """Test that get_risk_manager returns the same instance."""
        manager1 = get_risk_manager()
        manager2 = get_risk_manager()

        assert manager1 is manager2


class TestRiskManagerUpdateLimitsWithDB:
    """Tests for update_limits with database."""

    async def test_update_limits_creates_new(self, risk_manager_with_db, mock_db, tenant_id):
        """Test update_limits creates new config."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        limits = RiskLimits(
            max_position_size=20000,
            max_daily_loss=2000,
            max_order_value=10000,
        )

        result = await risk_manager_with_db.update_limits(tenant_id, limits)

        assert result == limits
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_limits_updates_existing(self, risk_manager_with_db, mock_db, tenant_id):
        """Test update_limits updates existing config."""
        mock_config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute.return_value = mock_result

        limits = RiskLimits(
            max_position_size=30000,
            max_daily_loss=3000,
            max_order_value=15000,
        )

        result = await risk_manager_with_db.update_limits(tenant_id, limits)

        assert result == limits
        assert mock_config.max_position_value == 30000
        assert mock_config.max_daily_loss_value == 3000
        mock_db.commit.assert_called_once()


class TestRiskManagerDrawdownWithDB:
    """Tests for drawdown methods with database."""

    async def test_get_current_drawdown_no_record(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test get_current_drawdown returns 0 when no record."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db.get_current_drawdown(tenant_id, session_id)

        assert result == 0.0

    async def test_get_current_drawdown_with_record(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test get_current_drawdown returns value from record."""
        mock_daily = MagicMock()
        mock_daily.max_drawdown_pct = 5.5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db.get_current_drawdown(tenant_id, session_id)

        assert result == 5.5


class TestRiskManagerDailyPnLWithDB:
    """Tests for update_daily_pnl with database."""

    async def test_update_daily_pnl_creates_record(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test update_daily_pnl creates new record."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        await risk_manager_with_db.update_daily_pnl(
            tenant_id=tenant_id,
            session_id=session_id,
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            equity=10150.0,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_daily_pnl_updates_existing(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test update_daily_pnl updates existing record."""
        mock_daily = MagicMock()
        mock_daily.equity_high = 10000.0
        mock_daily.equity_low = 9800.0
        mock_daily.max_drawdown_pct = 2.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        await risk_manager_with_db.update_daily_pnl(
            tenant_id=tenant_id,
            session_id=session_id,
            realized_pnl=200.0,
            unrealized_pnl=100.0,
            equity=10300.0,
        )

        assert mock_daily.realized_pnl == 200.0
        assert mock_daily.unrealized_pnl == 100.0
        assert mock_daily.total_pnl == 300.0
        assert mock_daily.equity_high == 10300.0  # New high
        mock_db.commit.assert_called_once()

    async def test_update_daily_pnl_calculates_drawdown(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test update_daily_pnl calculates drawdown correctly."""
        mock_daily = MagicMock()
        mock_daily.equity_high = 10000.0
        mock_daily.equity_low = 10000.0
        mock_daily.max_drawdown_pct = 0.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        # Equity dropped to 9500 = 5% drawdown
        await risk_manager_with_db.update_daily_pnl(
            tenant_id=tenant_id,
            session_id=session_id,
            realized_pnl=-500.0,
            unrealized_pnl=0.0,
            equity=9500.0,
        )

        assert mock_daily.equity_low == 9500.0
        assert mock_daily.max_drawdown_pct == 5.0


class TestRiskManagerRecordTradeWithDB:
    """Tests for record_trade with database."""

    async def test_record_trade_winning(self, risk_manager_with_db, mock_db, tenant_id, session_id):
        """Test record_trade increments winning trades."""
        mock_daily = MagicMock()
        mock_daily.trades_count = 5
        mock_daily.winning_trades = 3
        mock_daily.losing_trades = 2

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        await risk_manager_with_db.record_trade(tenant_id, session_id, is_win=True)

        assert mock_daily.trades_count == 6
        assert mock_daily.winning_trades == 4
        assert mock_daily.losing_trades == 2
        mock_db.commit.assert_called_once()

    async def test_record_trade_losing(self, risk_manager_with_db, mock_db, tenant_id, session_id):
        """Test record_trade increments losing trades."""
        mock_daily = MagicMock()
        mock_daily.trades_count = 5
        mock_daily.winning_trades = 3
        mock_daily.losing_trades = 2

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_daily
        mock_db.execute.return_value = mock_result

        await risk_manager_with_db.record_trade(tenant_id, session_id, is_win=False)

        assert mock_daily.trades_count == 6
        assert mock_daily.winning_trades == 3
        assert mock_daily.losing_trades == 3

    async def test_record_trade_no_record(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test record_trade handles missing record."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Should not raise
        await risk_manager_with_db.record_trade(tenant_id, session_id, is_win=True)
        mock_db.commit.assert_not_called()


class TestRiskManagerPositionSize:
    """Tests for position size checks."""

    async def test_check_position_size_no_position(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test _check_position_size with no existing position."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._check_position_size(
            tenant_id, session_id, "AAPL", 10, "buy", 10000
        )

        # 10 * 100 (default) = 1000 < 10000
        assert result is True

    async def test_check_position_size_exceeds(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test _check_position_size when exceeding limit."""
        mock_position = MagicMock()
        mock_position.qty = 50
        mock_position.current_price = 150.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_position
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._check_position_size(
            tenant_id, session_id, "AAPL", 50, "buy", 10000
        )

        # (50 + 50) * 150 = 15000 > 10000
        assert result is False

    async def test_check_position_size_sell_side(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test _check_position_size for sell orders."""
        mock_position = MagicMock()
        mock_position.qty = 50
        mock_position.current_price = 150.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_position
        mock_db.execute.return_value = mock_result

        result = await risk_manager_with_db._check_position_size(
            tenant_id, session_id, "AAPL", 20, "sell", 10000
        )

        # abs(50 - 20) * 150 = 4500 < 10000
        assert result is True


class TestRiskManagerPriceCache:
    """Tests for price caching behavior."""

    async def test_price_cached_after_fetch(self, risk_manager_with_db):
        """Test that price is cached after fetch."""
        mock_market_data = AsyncMock()
        mock_market_data.get_latest_price.return_value = 175.50
        risk_manager_with_db.market_data = mock_market_data

        price = await risk_manager_with_db._get_current_price("AAPL")

        assert price == 175.50
        assert risk_manager_with_db._price_cache["AAPL"] == 175.50

    async def test_price_uses_cache_on_failure(self, risk_manager_with_db):
        """Test that cached price is used when market data fails."""
        mock_market_data = AsyncMock()
        mock_market_data.get_latest_price.return_value = None
        risk_manager_with_db.market_data = mock_market_data
        risk_manager_with_db._price_cache["AAPL"] = 170.0

        price = await risk_manager_with_db._get_current_price("AAPL")

        assert price == 170.0

    async def test_price_fallback(self, risk_manager):
        """Test fallback price when no data available."""
        price = await risk_manager._get_current_price("UNKNOWN")

        assert price == 100.0  # Default fallback


class TestRiskManagerCheckDailyLoss:
    """Tests for check_daily_loss method."""

    async def test_check_daily_loss_under_limit(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test check_daily_loss returns True when under limit."""
        # Setup: session config, tenant config, daily P&L
        mock_result_session = MagicMock()
        mock_result_session.scalar_one_or_none.return_value = None

        mock_result_tenant = MagicMock()
        mock_result_tenant.scalar_one_or_none.return_value = None

        # Setup daily P&L
        mock_daily = MagicMock()
        mock_daily.total_pnl = -500  # Lost $500, limit is $1000

        mock_result_pnl = MagicMock()
        mock_result_pnl.scalar_one_or_none.return_value = mock_daily

        mock_db.execute.side_effect = [mock_result_session, mock_result_tenant, mock_result_pnl]

        result = await risk_manager_with_db.check_daily_loss(tenant_id, session_id)

        assert result is True

    async def test_check_daily_loss_exceeded(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test check_daily_loss returns False when exceeded."""
        # Setup: session config, tenant config, daily P&L
        mock_result_session = MagicMock()
        mock_result_session.scalar_one_or_none.return_value = None

        mock_result_tenant = MagicMock()
        mock_result_tenant.scalar_one_or_none.return_value = None

        mock_daily = MagicMock()
        mock_daily.total_pnl = -1500  # Lost $1500, limit is $1000

        mock_result_pnl = MagicMock()
        mock_result_pnl.scalar_one_or_none.return_value = mock_daily

        mock_db.execute.side_effect = [mock_result_session, mock_result_tenant, mock_result_pnl]

        result = await risk_manager_with_db.check_daily_loss(tenant_id, session_id)

        assert result is False


class TestRiskManagerGetLimitsWithConfig:
    """Tests for get_limits with config in database."""

    async def test_get_limits_with_session_config(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test get_limits returns session-specific config."""
        mock_config = MagicMock()
        mock_config.max_position_value = 20000
        mock_config.max_daily_loss_value = 2000
        mock_config.max_order_value = 10000
        mock_config.allowed_symbols = ["AAPL", "GOOGL"]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute.return_value = mock_result

        limits = await risk_manager_with_db.get_limits(tenant_id, session_id)

        assert limits.max_position_size == 20000
        assert limits.max_daily_loss == 2000
        assert limits.max_order_value == 10000
        assert limits.allowed_symbols == ["AAPL", "GOOGL"]

    async def test_get_limits_falls_back_to_tenant(
        self, risk_manager_with_db, mock_db, tenant_id, session_id
    ):
        """Test get_limits falls back to tenant-wide config."""
        mock_result_session = MagicMock()
        mock_result_session.scalar_one_or_none.return_value = None

        mock_config = MagicMock()
        mock_config.max_position_value = 15000
        mock_config.max_daily_loss_value = 1500
        mock_config.max_order_value = 7500
        mock_config.allowed_symbols = None

        mock_result_tenant = MagicMock()
        mock_result_tenant.scalar_one_or_none.return_value = mock_config

        mock_db.execute.side_effect = [mock_result_session, mock_result_tenant]

        limits = await risk_manager_with_db.get_limits(tenant_id, session_id)

        assert limits.max_position_size == 15000
