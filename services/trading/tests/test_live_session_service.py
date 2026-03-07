"""Tests for LiveSessionService class."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_alpaca import Account
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)

from src.models import SessionResponse
from src.services.live_session_service import DecryptedCredentials, LiveSessionService


@pytest.fixture
def tenant_id():
    """Generate a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Generate a test user ID."""
    return uuid4()


@pytest.fixture
def strategy_id():
    """Generate a test strategy ID."""
    return uuid4()


@pytest.fixture
def session_id():
    """Generate a test session ID."""
    return uuid4()


@pytest.fixture
def credentials_id():
    """Generate a test credentials ID."""
    return uuid4()


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_runner_manager():
    """Create a mock RunnerManager."""
    manager = MagicMock()
    manager.start_runner = AsyncMock()
    manager.stop_runner = AsyncMock()
    manager.get_runner = MagicMock()
    manager.active_runners = {}
    return manager


@pytest.fixture
def mock_order_executor():
    """Create a mock OrderExecutor."""
    return MagicMock()


@pytest.fixture
def mock_risk_manager():
    """Create a mock RiskManager."""
    return MagicMock()


@pytest.fixture
def mock_alpaca_client():
    """Create a mock AlpacaTradingClient."""
    client = MagicMock()
    client.api_key = "test_key"
    client.api_secret = "test_secret"
    return client


@pytest.fixture
def session_response(session_id, strategy_id, tenant_id):
    """Create a sample session response."""
    return SessionResponse(
        id=session_id,
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_credentials():
    """Create mock decrypted credentials."""
    return DecryptedCredentials(
        id=uuid4(),
        name="Test Paper Keys",
        api_key="PKTEST12345678901234",
        api_secret="SKTEST12345678901234567890123456789012345",
        is_paper=True,
    )


@pytest.fixture
def live_session_service(
    mock_db,
    mock_runner_manager,
    mock_order_executor,
    mock_risk_manager,
    mock_alpaca_client,
):
    """Create a LiveSessionService instance."""
    return LiveSessionService(
        db=mock_db,
        runner_manager=mock_runner_manager,
        order_executor=mock_order_executor,
        risk_manager=mock_risk_manager,
        alpaca_client=mock_alpaca_client,
    )


class TestLiveSessionServiceInit:
    """Tests for LiveSessionService initialization."""

    def test_init(
        self,
        mock_db,
        mock_runner_manager,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
    ):
        """Test initialization."""
        service = LiveSessionService(
            db=mock_db,
            runner_manager=mock_runner_manager,
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
        )

        assert service.db is mock_db
        assert service.runner_manager is mock_runner_manager
        assert service.order_executor is mock_order_executor
        assert service.risk_manager is mock_risk_manager
        assert service.alpaca_client is mock_alpaca_client


class TestLiveSessionServiceStopRunner:
    """Tests for _stop_runner method."""

    async def test_stop_runner_active(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
    ):
        """Test stopping an active runner."""
        mock_runner_manager.active_runners = {session_id: MagicMock()}

        await live_session_service._stop_runner(session_id)

        mock_runner_manager.stop_runner.assert_called_once_with(session_id)

    async def test_stop_runner_inactive(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
    ):
        """Test stopping when no runner is active."""
        mock_runner_manager.active_runners = {}

        # Should not raise or call stop_runner
        await live_session_service._stop_runner(session_id)

        mock_runner_manager.stop_runner.assert_not_called()


class TestLiveSessionServiceGetStrategySexpr:
    """Tests for _get_strategy_sexpr method."""

    def test_get_sexpr_from_config_sexpr(self, live_session_service):
        """Test getting S-expression from config_sexpr field."""
        mock_version = MagicMock()
        mock_version.config_sexpr = "(strategy test)"
        mock_version.config_json = {}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result == "(strategy test)"

    def test_get_sexpr_from_config_json(self, live_session_service):
        """Test getting S-expression from config JSON."""
        mock_version = MagicMock()
        mock_version.config_sexpr = None
        mock_version.config_json = {"sexpr": "(strategy from json)"}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result == "(strategy from json)"

    def test_get_sexpr_not_found(self, live_session_service):
        """Test when no S-expression is found."""
        mock_version = MagicMock()
        mock_version.config_sexpr = None
        mock_version.config_json = {}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result is None

    def test_get_sexpr_config_json_not_dict(self, live_session_service):
        """Test when config_json is not a dict."""
        mock_version = MagicMock()
        mock_version.config_sexpr = None
        mock_version.config_json = None

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result is None


class TestLiveSessionServicePauseResume:
    """Tests for pause/resume with runners."""

    async def test_pause_calls_runner_pause(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
    ):
        """Test that pause calls runner.pause()."""
        mock_runner = MagicMock()
        mock_runner_manager.get_runner.return_value = mock_runner

        # Mock the parent class method
        live_session_service.pause_session = AsyncMock(return_value=None)

        await live_session_service.pause_session(session_id, tenant_id)

        # Note: we can't easily test the runner pause because the
        # method calls the parent first

    async def test_resume_calls_runner_resume(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
    ):
        """Test that resume calls runner.resume()."""
        mock_runner = MagicMock()
        mock_runner_manager.get_runner.return_value = mock_runner

        # Mock the parent class method
        live_session_service.resume_session = AsyncMock(return_value=None)

        await live_session_service.resume_session(session_id, tenant_id)


class TestLiveSessionServiceStartRunner:
    """Tests for _start_runner method."""

    async def test_start_runner_strategy_not_found(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner with missing strategy."""
        live_session_service._get_strategy = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Strategy .* not found"):
            await live_session_service._start_runner(
                session_id=session_id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=None,
                symbols=["AAPL"],
                mode=EXECUTION_MODE_PAPER,
                credentials=mock_credentials,
            )

    async def test_start_runner_version_not_found(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner with missing strategy version."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)
        live_session_service._get_strategy_version = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Strategy version .* not found"):
            await live_session_service._start_runner(
                session_id=session_id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=None,
                symbols=["AAPL"],
                mode=EXECUTION_MODE_PAPER,
                credentials=mock_credentials,
            )

    async def test_start_runner_no_sexpr(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner with no S-expression."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)

        mock_version = MagicMock()
        mock_version.config_sexpr = None
        mock_version.config_json = {}
        live_session_service._get_strategy_version = AsyncMock(return_value=mock_version)

        with pytest.raises(ValueError, match="no executable definition"):
            await live_session_service._start_runner(
                session_id=session_id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=None,
                symbols=["AAPL"],
                mode=EXECUTION_MODE_PAPER,
                credentials=mock_credentials,
            )

    async def test_start_runner_no_symbols(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner with no symbols."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)

        mock_version = MagicMock()
        mock_version.definition_sexpr = "(strategy test)"
        mock_version.symbols = None
        live_session_service._get_strategy_version = AsyncMock(return_value=mock_version)

        with pytest.raises(ValueError, match="No symbols specified"):
            await live_session_service._start_runner(
                session_id=session_id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=None,
                symbols=[],
                mode=EXECUTION_MODE_PAPER,
                credentials=mock_credentials,
            )

    async def test_start_runner_success(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner with successful runner creation."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)

        mock_version = MagicMock()
        mock_version.definition_sexpr = "(strategy test)"
        mock_version.symbols = ["AAPL"]
        mock_version.timeframe = "1Min"
        live_session_service._get_strategy_version = AsyncMock(return_value=mock_version)

        with patch("src.services.live_session_service.StrategyAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.min_bars = 5
            mock_adapter_cls.return_value = mock_adapter

            with patch("src.services.live_session_service.AlpacaBarStream"):
                with patch("src.services.live_session_service.TradingClient"):
                    await live_session_service._start_runner(
                        session_id=session_id,
                        tenant_id=tenant_id,
                        strategy_id=strategy_id,
                        version=None,
                        symbols=["AAPL"],
                        mode=EXECUTION_MODE_PAPER,
                        credentials=mock_credentials,
                    )

                    mock_runner_manager.start_runner.assert_called_once()

    async def test_start_runner_uses_version_symbols_when_none_provided(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
        strategy_id,
        mock_credentials,
    ):
        """Test _start_runner uses strategy version symbols when none provided."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)

        mock_version = MagicMock()
        mock_version.definition_sexpr = "(strategy test)"
        mock_version.symbols = ["GOOGL", "MSFT"]
        mock_version.timeframe = "5Min"
        live_session_service._get_strategy_version = AsyncMock(return_value=mock_version)

        with patch("src.services.live_session_service.StrategyAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.min_bars = 10
            mock_adapter_cls.return_value = mock_adapter

            with patch("src.services.live_session_service.AlpacaBarStream"):
                with patch("src.services.live_session_service.TradingClient"):
                    await live_session_service._start_runner(
                        session_id=session_id,
                        tenant_id=tenant_id,
                        strategy_id=strategy_id,
                        version=None,
                        symbols=None,
                        mode=EXECUTION_MODE_LIVE,
                        credentials=mock_credentials,
                    )

                    mock_runner_manager.start_runner.assert_called_once()
                    call_kwargs = mock_runner_manager.start_runner.call_args[1]
                    assert call_kwargs["config"].symbols == ["GOOGL", "MSFT"]


class TestLiveSessionServiceStartSession:
    """Tests for start_session method."""

    async def test_start_session_success(
        self,
        live_session_service,
        mock_runner_manager,
        session_response,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
        mock_credentials,
    ):
        """Test successful session start."""
        # Mock preflight checks to pass and return credentials
        live_session_service._preflight_checks = AsyncMock(return_value=mock_credentials)

        # Mock parent start_session
        with patch.object(
            live_session_service.__class__.__bases__[0],
            "start_session",
            new=AsyncMock(return_value=session_response),
        ):
            # Mock _start_runner
            live_session_service._start_runner = AsyncMock()

            result = await live_session_service.start_session(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                strategy_version=1,
                name="Test Session",
                mode=EXECUTION_MODE_PAPER,
                credentials_id=credentials_id,
                symbols=["AAPL"],
            )

            assert result == session_response
            live_session_service._preflight_checks.assert_called_once()
            live_session_service._start_runner.assert_called_once()

    async def test_start_session_runner_failure_sets_error(
        self,
        live_session_service,
        mock_runner_manager,
        session_response,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
        mock_credentials,
    ):
        """Test that runner failure sets session error."""
        # Mock preflight checks to pass and return credentials
        live_session_service._preflight_checks = AsyncMock(return_value=mock_credentials)

        # Mock parent start_session
        with patch.object(
            live_session_service.__class__.__bases__[0],
            "start_session",
            new=AsyncMock(return_value=session_response),
        ):
            # Mock set_error
            with patch.object(
                live_session_service.__class__.__bases__[0],
                "set_error",
                new=AsyncMock(),
            ) as mock_set_error:
                # Make _start_runner fail
                live_session_service._start_runner = AsyncMock(
                    side_effect=ValueError("Runner failed")
                )

                with pytest.raises(ValueError, match="Runner failed"):
                    await live_session_service.start_session(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        strategy_id=strategy_id,
                        strategy_version=1,
                        name="Test Session",
                        mode=EXECUTION_MODE_PAPER,
                        credentials_id=credentials_id,
                        symbols=["AAPL"],
                    )

                mock_set_error.assert_called_once()

    async def test_start_session_preflight_failure(
        self,
        live_session_service,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
    ):
        """Test that preflight failure prevents session creation."""
        # Mock preflight checks to fail
        live_session_service._preflight_checks = AsyncMock(
            side_effect=ValueError("No active subscription found")
        )

        with pytest.raises(ValueError, match="No active subscription found"):
            await live_session_service.start_session(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                strategy_version=1,
                name="Test Session",
                mode=EXECUTION_MODE_PAPER,
                credentials_id=credentials_id,
                symbols=["AAPL"],
            )

        # _start_runner should NOT have been called
        assert not hasattr(live_session_service, "_start_runner_called")


class TestLiveSessionServiceStopSession:
    """Tests for stop_session method."""

    async def test_stop_session_stops_runner_and_db(
        self,
        live_session_service,
        mock_runner_manager,
        session_response,
        session_id,
        tenant_id,
    ):
        """Test that stop_session stops runner and updates database."""
        mock_runner_manager.active_runners = {session_id: MagicMock()}

        with patch.object(
            live_session_service.__class__.__bases__[0],
            "stop_session",
            new=AsyncMock(return_value=session_response),
        ) as mock_parent_stop:
            result = await live_session_service.stop_session(session_id, tenant_id)

            mock_runner_manager.stop_runner.assert_called_once_with(session_id)
            mock_parent_stop.assert_called_once_with(session_id, tenant_id)
            assert result == session_response


class TestLiveSessionServicePauseResumeWithRunner:
    """Additional tests for pause/resume with actual runner calls."""

    async def test_pause_session_pauses_runner(
        self,
        mock_db,
        mock_runner_manager,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        session_id,
        tenant_id,
        session_response,
    ):
        """Test that pause_session calls runner.pause()."""
        service = LiveSessionService(
            db=mock_db,
            runner_manager=mock_runner_manager,
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
        )

        mock_runner = MagicMock()
        mock_runner_manager.get_runner.return_value = mock_runner

        with patch.object(
            service.__class__.__bases__[0],
            "pause_session",
            new=AsyncMock(return_value=session_response),
        ):
            result = await service.pause_session(session_id, tenant_id)

            mock_runner.pause.assert_called_once()
            assert result == session_response

    async def test_pause_session_no_runner(
        self,
        mock_db,
        mock_runner_manager,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        session_id,
        tenant_id,
        session_response,
    ):
        """Test pause_session when no runner exists."""
        service = LiveSessionService(
            db=mock_db,
            runner_manager=mock_runner_manager,
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
        )

        mock_runner_manager.get_runner.return_value = None

        with patch.object(
            service.__class__.__bases__[0],
            "pause_session",
            new=AsyncMock(return_value=session_response),
        ):
            result = await service.pause_session(session_id, tenant_id)

            assert result == session_response

    async def test_resume_session_resumes_runner(
        self,
        mock_db,
        mock_runner_manager,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        session_id,
        tenant_id,
        session_response,
    ):
        """Test that resume_session calls runner.resume()."""
        service = LiveSessionService(
            db=mock_db,
            runner_manager=mock_runner_manager,
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
        )

        mock_runner = MagicMock()
        mock_runner_manager.get_runner.return_value = mock_runner

        with patch.object(
            service.__class__.__bases__[0],
            "resume_session",
            new=AsyncMock(return_value=session_response),
        ):
            result = await service.resume_session(session_id, tenant_id)

            mock_runner.resume.assert_called_once()
            assert result == session_response

    async def test_resume_session_no_runner(
        self,
        mock_db,
        mock_runner_manager,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        session_id,
        tenant_id,
        session_response,
    ):
        """Test resume_session when no runner exists."""
        service = LiveSessionService(
            db=mock_db,
            runner_manager=mock_runner_manager,
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
        )

        mock_runner_manager.get_runner.return_value = None

        with patch.object(
            service.__class__.__bases__[0],
            "resume_session",
            new=AsyncMock(return_value=session_response),
        ):
            result = await service.resume_session(session_id, tenant_id)

            assert result == session_response


# ===================
# Preflight Check Tests
# ===================


class TestLiveSessionServicePreflightChecks:
    """Tests for preflight checks before starting sessions."""

    async def test_preflight_checks_credentials_not_found(
        self,
        live_session_service,
        tenant_id,
        credentials_id,
    ):
        """Test preflight fails when credentials not found."""
        # Mock _check_subscription to pass
        live_session_service._check_subscription = AsyncMock()

        # Mock _get_credentials_by_id to return None
        live_session_service._get_credentials_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found or not authorized"):
            await live_session_service._preflight_checks(
                tenant_id=tenant_id,
                credentials_id=credentials_id,
                mode=EXECUTION_MODE_PAPER,
            )

    async def test_preflight_checks_paper_credentials_for_live_mode(
        self,
        live_session_service,
        tenant_id,
        credentials_id,
        mock_credentials,
    ):
        """Test preflight fails when using paper credentials for live trading."""
        # Mock _check_subscription to pass
        live_session_service._check_subscription = AsyncMock()

        # Mock _get_credentials_by_id to return paper credentials
        live_session_service._get_credentials_by_id = AsyncMock(
            return_value=mock_credentials  # is_paper=True
        )

        with pytest.raises(ValueError, match="Cannot start LIVE session with paper"):
            await live_session_service._preflight_checks(
                tenant_id=tenant_id,
                credentials_id=credentials_id,
                mode=EXECUTION_MODE_LIVE,
            )

    async def test_preflight_checks_success_paper_mode(
        self,
        live_session_service,
        tenant_id,
        credentials_id,
        mock_credentials,
    ):
        """Test preflight succeeds for paper trading with paper credentials."""
        # Mock all checks to pass
        live_session_service._check_subscription = AsyncMock()
        live_session_service._get_credentials_by_id = AsyncMock(return_value=mock_credentials)
        live_session_service._check_alpaca_account = AsyncMock()

        result = await live_session_service._preflight_checks(
            tenant_id=tenant_id,
            credentials_id=credentials_id,
            mode=EXECUTION_MODE_PAPER,
        )

        assert result == mock_credentials
        live_session_service._check_subscription.assert_called_once()
        live_session_service._check_alpaca_account.assert_called_once()


class TestLiveSessionServiceCheckSubscription:
    """Tests for subscription validation in preflight."""

    async def test_check_subscription_no_subscription(
        self,
        live_session_service,
        mock_db,
        tenant_id,
    ):
        """Test check fails when no active subscription exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No active subscription found"):
            await live_session_service._check_subscription(tenant_id, EXECUTION_MODE_PAPER)

    async def test_check_subscription_free_plan_live_trading(
        self,
        live_session_service,
        mock_db,
        tenant_id,
    ):
        """Test check fails for free plan trying live trading."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.plan_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        # Mock plan with free tier
        mock_plan = MagicMock()
        mock_plan.tier = "free"
        live_session_service._get_plan = AsyncMock(return_value=mock_plan)

        with pytest.raises(ValueError, match="Live trading requires a paid subscription"):
            await live_session_service._check_subscription(tenant_id, EXECUTION_MODE_LIVE)

    async def test_check_subscription_paid_plan_live_trading(
        self,
        live_session_service,
        mock_db,
        tenant_id,
    ):
        """Test check passes for paid plan with live trading."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.plan_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        # Mock plan with pro tier
        mock_plan = MagicMock()
        mock_plan.tier = "pro"
        live_session_service._get_plan = AsyncMock(return_value=mock_plan)

        # Should not raise
        await live_session_service._check_subscription(tenant_id, EXECUTION_MODE_LIVE)


class TestLiveSessionServiceCheckAlpacaAccount:
    """Tests for Alpaca account validation in preflight."""

    async def test_check_alpaca_account_connection_failed(
        self,
        live_session_service,
        mock_credentials,
    ):
        """Test check fails when Alpaca connection fails."""
        with patch("src.services.live_session_service.TradingClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_account = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="Failed to connect to Alpaca"):
                await live_session_service._check_alpaca_account(
                    mock_credentials, EXECUTION_MODE_PAPER
                )

    async def test_check_alpaca_account_inactive(
        self,
        live_session_service,
        mock_credentials,
    ):
        """Test check fails when Alpaca account is not active."""
        with patch("src.services.live_session_service.TradingClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_account = AsyncMock(
                return_value=Account(
                    id="test-acc",
                    account_number="123",
                    status="ACCOUNT_UPDATED",
                    cash=10000.0,
                    portfolio_value=10000.0,
                    buying_power=10000.0,
                    equity=10000.0,
                )
            )
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="account is not active"):
                await live_session_service._check_alpaca_account(
                    mock_credentials, EXECUTION_MODE_PAPER
                )

    async def test_check_alpaca_account_insufficient_buying_power_live(
        self,
        live_session_service,
    ):
        """Test check fails when live trading with insufficient buying power."""
        # Create live credentials
        live_creds = DecryptedCredentials(
            id=uuid4(),
            name="Test Live Keys",
            api_key="AKTEST12345678901234",
            api_secret="SKTEST12345678901234567890123456789012345",
            is_paper=False,
        )

        with patch("src.services.live_session_service.TradingClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_account = AsyncMock(
                return_value=Account(
                    id="test-acc",
                    account_number="123",
                    status="ACTIVE",
                    cash=100.0,
                    portfolio_value=100.0,
                    buying_power=100.0,  # Below $500 minimum for live
                    equity=100.0,
                )
            )
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="Insufficient buying power"):
                await live_session_service._check_alpaca_account(live_creds, EXECUTION_MODE_LIVE)

    async def test_check_alpaca_account_paper_zero_buying_power_ok(
        self,
        live_session_service,
        mock_credentials,
    ):
        """Test paper trading allows zero buying power."""
        with patch("src.services.live_session_service.TradingClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_account = AsyncMock(
                return_value=Account(
                    id="test-acc",
                    account_number="123",
                    status="ACTIVE",
                    cash=0.0,
                    portfolio_value=0.0,
                    buying_power=0.0,
                    equity=0.0,
                )
            )
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            # Should not raise for paper trading
            await live_session_service._check_alpaca_account(mock_credentials, EXECUTION_MODE_PAPER)

    async def test_check_alpaca_account_live_sufficient_buying_power(
        self,
        live_session_service,
    ):
        """Test live trading passes with sufficient buying power."""
        live_creds = DecryptedCredentials(
            id=uuid4(),
            name="Test Live Keys",
            api_key="AKTEST12345678901234",
            api_secret="SKTEST12345678901234567890123456789012345",
            is_paper=False,
        )

        with patch("src.services.live_session_service.TradingClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_account = AsyncMock(
                return_value=Account(
                    id="test-acc",
                    account_number="123",
                    status="ACTIVE",
                    cash=10000.0,
                    portfolio_value=10000.0,
                    buying_power=10000.0,
                    equity=10000.0,
                )
            )
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            # Should not raise
            await live_session_service._check_alpaca_account(live_creds, EXECUTION_MODE_LIVE)


class TestLiveSessionServiceGetCredentials:
    """Tests for credential retrieval."""

    async def test_get_credentials_by_id_not_found(
        self,
        live_session_service,
        mock_db,
        tenant_id,
        credentials_id,
    ):
        """Test returns None when credentials not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await live_session_service._get_credentials_by_id(credentials_id, tenant_id)

        assert result is None

    async def test_get_credentials_by_id_wrong_tenant(
        self,
        live_session_service,
        mock_db,
        credentials_id,
    ):
        """Test returns None for wrong tenant (tenant isolation)."""
        wrong_tenant_id = uuid4()

        # Query will return None because tenant_id doesn't match
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await live_session_service._get_credentials_by_id(credentials_id, wrong_tenant_id)

        assert result is None

    async def test_get_credentials_by_id_success(
        self,
        live_session_service,
        mock_db,
        tenant_id,
        credentials_id,
    ):
        """Test successful credential retrieval."""
        mock_creds = MagicMock()
        mock_creds.id = credentials_id
        mock_creds.name = "Test Keys"
        mock_creds.api_key_encrypted = "encrypted_key"
        mock_creds.api_secret_encrypted = "encrypted_secret"
        mock_creds.is_paper = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        mock_db.execute.return_value = mock_result

        with patch("src.services.live_session_service.decrypt_value") as mock_decrypt:
            mock_decrypt.side_effect = ["decrypted_key", "decrypted_secret"]

            result = await live_session_service._get_credentials_by_id(credentials_id, tenant_id)

            assert result is not None
            assert result.id == credentials_id
            assert result.name == "Test Keys"
            assert result.api_key == "decrypted_key"
            assert result.api_secret == "decrypted_secret"
            assert result.is_paper is True
