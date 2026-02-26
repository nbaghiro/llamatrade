"""Test session service."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models import SessionStatus, TradingMode
from src.services.session_service import SessionService


@pytest.fixture
def session_service(mock_db):
    """Create session service with mocked database."""
    return SessionService(mock_db)


class TestStartSession:
    """Tests for start_session."""

    async def test_start_session_success(
        self,
        session_service,
        mock_db,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
    ):
        """Test starting a new session successfully."""
        # Mock strategy lookup
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1
        mock_strategy.id = strategy_id
        mock_strategy.tenant_id = tenant_id

        mock_strategy_version = MagicMock()
        mock_strategy_version.symbols = ["AAPL", "GOOGL"]

        # Setup execute mock to return strategy and version
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_strategy, mock_strategy_version]
        mock_db.execute.return_value = mock_result

        # Mock the added session
        mock_db.refresh = AsyncMock(side_effect=lambda s: setattr(s, "id", strategy_id))

        result = await session_service.start_session(
            tenant_id=tenant_id,
            user_id=user_id,
            strategy_id=strategy_id,
            strategy_version=None,
            name="Test Session",
            mode=TradingMode.PAPER,
            credentials_id=credentials_id,
        )

        assert result is not None
        assert result.strategy_id == strategy_id
        assert result.mode == TradingMode.PAPER
        assert result.status == SessionStatus.ACTIVE
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_start_session_strategy_not_found(
        self,
        session_service,
        mock_db,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
    ):
        """Test error when strategy doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await session_service.start_session(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                strategy_version=None,
                name="Test Session",
                mode=TradingMode.PAPER,
                credentials_id=credentials_id,
            )

    async def test_start_session_no_symbols(
        self,
        session_service,
        mock_db,
        tenant_id,
        user_id,
        strategy_id,
        credentials_id,
    ):
        """Test error when no symbols specified."""
        mock_strategy = MagicMock()
        mock_strategy.current_version = 1

        mock_strategy_version = MagicMock()
        mock_strategy_version.symbols = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_strategy, mock_strategy_version]
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No symbols"):
            await session_service.start_session(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                strategy_version=None,
                name="Test Session",
                mode=TradingMode.PAPER,
                credentials_id=credentials_id,
            )


class TestGetSession:
    """Tests for get_session."""

    async def test_get_session_found(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test getting an existing session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.get_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        assert result.id == session_id

    async def test_get_session_not_found(
        self,
        session_service,
        mock_db,
        tenant_id,
        session_id,
    ):
        """Test getting a non-existent session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await session_service.get_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is None


class TestStopSession:
    """Tests for stop_session."""

    async def test_stop_active_session(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test stopping an active session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.stop_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        assert mock_trading_session.status == "stopped"
        assert mock_trading_session.stopped_at is not None
        mock_db.commit.assert_called()

    async def test_stop_already_stopped_session(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test stopping an already stopped session (no-op)."""
        mock_trading_session.status = "stopped"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.stop_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is not None


class TestPauseResumeSession:
    """Tests for pause_session and resume_session."""

    async def test_pause_active_session(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test pausing an active session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.pause_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        assert mock_trading_session.status == "paused"
        mock_db.commit.assert_called()

    async def test_pause_non_active_session_error(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test error when pausing a non-active session."""
        mock_trading_session.status = "stopped"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Only active sessions"):
            await session_service.pause_session(
                session_id=session_id,
                tenant_id=tenant_id,
            )

    async def test_resume_paused_session(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test resuming a paused session."""
        mock_trading_session.status = "paused"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.resume_session(
            session_id=session_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        assert mock_trading_session.status == "active"
        mock_db.commit.assert_called()

    async def test_resume_non_paused_session_error(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test error when resuming a non-paused session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Only paused sessions"):
            await session_service.resume_session(
                session_id=session_id,
                tenant_id=tenant_id,
            )


class TestSetError:
    """Tests for set_error."""

    async def test_set_error_on_session(
        self,
        session_service,
        mock_db,
        mock_trading_session,
        tenant_id,
        session_id,
    ):
        """Test setting error state on a session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trading_session
        mock_db.execute.return_value = mock_result

        result = await session_service.set_error(
            session_id=session_id,
            tenant_id=tenant_id,
            error_message="Connection lost",
        )

        assert result is not None
        assert mock_trading_session.status == "error"
        assert mock_trading_session.error_message == "Connection lost"
        assert mock_trading_session.stopped_at is not None
        mock_db.commit.assert_called()
