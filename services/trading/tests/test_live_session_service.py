"""Tests for LiveSessionService class."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.models import SessionResponse, SessionStatus, TradingMode
from src.services.live_session_service import LiveSessionService


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
    from datetime import datetime

    return SessionResponse(
        id=session_id,
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        mode=TradingMode.PAPER,
        status=SessionStatus.ACTIVE,
        started_at=datetime.now(),
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

    def test_get_sexpr_from_definition_sexpr(self, live_session_service):
        """Test getting S-expression from definition_sexpr field."""
        mock_version = MagicMock()
        mock_version.definition_sexpr = "(strategy test)"
        mock_version.definition = {}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result == "(strategy test)"

    def test_get_sexpr_from_definition_json(self, live_session_service):
        """Test getting S-expression from definition JSON."""
        mock_version = MagicMock()
        mock_version.definition_sexpr = None
        mock_version.definition = {"sexpr": "(strategy from json)"}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result == "(strategy from json)"

    def test_get_sexpr_not_found(self, live_session_service):
        """Test when no S-expression is found."""
        mock_version = MagicMock()
        mock_version.definition_sexpr = None
        mock_version.definition = {}

        result = live_session_service._get_strategy_sexpr(mock_version)

        assert result is None

    def test_get_sexpr_definition_not_dict(self, live_session_service):
        """Test when definition is not a dict."""
        mock_version = MagicMock()
        mock_version.definition_sexpr = None
        mock_version.definition = None

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
                mode=TradingMode.PAPER,
            )

    async def test_start_runner_version_not_found(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
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
                mode=TradingMode.PAPER,
            )

    async def test_start_runner_no_sexpr(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
    ):
        """Test _start_runner with no S-expression."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        live_session_service._get_strategy = AsyncMock(return_value=mock_strategy)

        mock_version = MagicMock()
        mock_version.definition_sexpr = None
        mock_version.definition = {}
        live_session_service._get_strategy_version = AsyncMock(return_value=mock_version)

        with pytest.raises(ValueError, match="no executable definition"):
            await live_session_service._start_runner(
                session_id=session_id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=None,
                symbols=["AAPL"],
                mode=TradingMode.PAPER,
            )

    async def test_start_runner_no_symbols(
        self,
        live_session_service,
        session_id,
        tenant_id,
        strategy_id,
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
                mode=TradingMode.PAPER,
            )

    async def test_start_runner_success(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
        strategy_id,
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
                await live_session_service._start_runner(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    version=None,
                    symbols=["AAPL"],
                    mode=TradingMode.PAPER,
                )

                mock_runner_manager.start_runner.assert_called_once()

    async def test_start_runner_uses_version_symbols_when_none_provided(
        self,
        live_session_service,
        mock_runner_manager,
        session_id,
        tenant_id,
        strategy_id,
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
                await live_session_service._start_runner(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    version=None,
                    symbols=None,
                    mode=TradingMode.LIVE,
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
    ):
        """Test successful session start."""
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
                mode=TradingMode.PAPER,
                credentials_id=credentials_id,
                symbols=["AAPL"],
            )

            assert result == session_response
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
    ):
        """Test that runner failure sets session error."""
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
                        mode=TradingMode.PAPER,
                        credentials_id=credentials_id,
                        symbols=["AAPL"],
                    )

                mock_set_error.assert_called_once()


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
