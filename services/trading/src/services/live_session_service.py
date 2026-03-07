"""Live session service - session management with runner lifecycle integration.

Extends SessionService to integrate with StrategyRunner for live trading.
When sessions start, runners start. When sessions stop, runners stop.

Safety features:
- Preflight checks before starting sessions (subscription, credentials, buying power)
- Per-tenant credential isolation via database query
- Credential mode validation (paper credentials can't be used for live trading)
"""

import logging
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_alpaca import TradingClient, get_trading_client
from llamatrade_common.utils import decrypt_value
from llamatrade_db import get_db
from llamatrade_db.models.auth import AlpacaCredentials
from llamatrade_db.models.billing import Plan, Subscription
from llamatrade_db.models.strategy import StrategyVersion
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
)

from src.compiler_adapter import StrategyAdapter
from src.executor.order_executor import OrderExecutor, get_order_executor
from src.models import SessionResponse
from src.risk.risk_manager import RiskManager, get_risk_manager
from src.runner.bar_stream import AlpacaBarStream, StreamConfig
from src.runner.runner import RunnerConfig, RunnerManager, get_runner_manager
from src.runner.trade_stream import AlpacaTradeStream, TradeStreamConfig
from src.services.session_service import SessionService

logger = logging.getLogger(__name__)


class DecryptedCredentials(BaseModel):
    """Decrypted Alpaca credentials for internal use."""

    id: UUID
    name: str
    api_key: str
    api_secret: str
    is_paper: bool


class LiveSessionService(SessionService):
    """Session service with integrated runner lifecycle management.

    When a session is started, a StrategyRunner is created and started.
    When a session is stopped, the runner is stopped.
    When a session is paused/resumed, the runner is paused/resumed.
    """

    def __init__(
        self,
        db: AsyncSession,
        runner_manager: RunnerManager,
        order_executor: OrderExecutor,
        risk_manager: RiskManager,
        alpaca_client: TradingClient,
    ):
        super().__init__(db)
        self.runner_manager = runner_manager
        self.order_executor = order_executor
        self.risk_manager = risk_manager
        self.alpaca_client = alpaca_client

    async def start_session(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int | None,
        name: str,
        mode: int,  # ExecutionMode proto value: PAPER=1, LIVE=2
        credentials_id: UUID,
        symbols: list[str] | None = None,
        config: dict[str, object] | None = None,
    ) -> SessionResponse:
        """Start a new trading session with runner.

        Creates the session in database and starts a StrategyRunner
        to execute the strategy in real-time.

        Raises:
            ValueError: If preflight checks fail (subscription, credentials, buying power)
        """
        # Run preflight checks BEFORE creating session
        creds = await self._preflight_checks(
            tenant_id=tenant_id,
            credentials_id=credentials_id,
            mode=mode,
        )

        # Create session in database
        response = await super().start_session(
            tenant_id=tenant_id,
            user_id=user_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            name=name,
            mode=mode,
            credentials_id=credentials_id,
            symbols=symbols,
            config=config,
        )

        # Load strategy and start runner
        try:
            await self._start_runner(
                session_id=response.id,
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=strategy_version,
                symbols=symbols,
                mode=mode,
                credentials=creds,
            )
        except Exception as e:
            logger.error(f"Failed to start runner for session {response.id}: {e}")
            # Update session status to error
            await super().set_error(response.id, tenant_id, str(e))
            raise

        return response

    async def stop_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Stop a trading session and its runner."""
        # Stop runner first
        await self._stop_runner(session_id)

        # Then update database
        return await super().stop_session(session_id, tenant_id)

    async def pause_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Pause a trading session and its runner."""
        # Pause the runner
        runner = self.runner_manager.get_runner(session_id)
        if runner:
            runner.pause()

        # Update database
        return await super().pause_session(session_id, tenant_id)

    async def resume_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Resume a paused session and its runner."""
        # Resume the runner
        runner = self.runner_manager.get_runner(session_id)
        if runner:
            runner.resume()

        # Update database
        return await super().resume_session(session_id, tenant_id)

    # ===================
    # Runner management
    # ===================

    async def _start_runner(
        self,
        session_id: UUID,
        tenant_id: UUID,
        strategy_id: UUID,
        version: int | None,
        symbols: list[str] | None,
        mode: int,  # ExecutionMode proto value: PAPER=1, LIVE=2
        credentials: DecryptedCredentials,
    ) -> None:
        """Create and start a runner for the session.

        Args:
            session_id: The trading session ID
            tenant_id: Tenant ID for isolation
            strategy_id: Strategy to execute
            version: Strategy version (None = current)
            symbols: Symbols to trade (None = from strategy)
            mode: ExecutionMode proto value (PAPER=1, LIVE=2)
            credentials: Decrypted Alpaca credentials for this session
        """
        # Get strategy version with S-expression
        strategy = await self._get_strategy(tenant_id, strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        actual_version = version or strategy.current_version
        strategy_ver = await self._get_strategy_version(strategy_id, actual_version)
        if not strategy_ver:
            raise ValueError(f"Strategy version {actual_version} not found")

        # Get strategy definition
        strategy_sexpr = self._get_strategy_sexpr(strategy_ver)
        if not strategy_sexpr:
            raise ValueError("Strategy has no executable definition")

        # Get symbols
        actual_symbols = symbols or strategy_ver.symbols or []
        if not actual_symbols:
            raise ValueError("No symbols specified")

        # Create strategy adapter
        strategy_fn = StrategyAdapter(strategy_sexpr)

        # Create bar stream with session-specific credentials
        stream_config = StreamConfig(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
        )
        bar_stream = AlpacaBarStream(stream_config)

        # Create trade stream with same credentials
        trade_config = TradeStreamConfig(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
        )
        trade_stream = AlpacaTradeStream(trade_config)

        # Create Alpaca client with session-specific credentials
        session_alpaca_client = TradingClient(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
        )

        # Create runner config
        runner_config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=actual_symbols,
            timeframe=strategy_ver.timeframe or "1Min",
            warmup_bars=strategy_fn.min_bars + 10,  # Extra buffer
        )

        # Start the runner with session-specific client
        await self.runner_manager.start_runner(
            config=runner_config,
            strategy_fn=strategy_fn,
            bar_stream=bar_stream,
            trade_stream=trade_stream,
            order_executor=self.order_executor,
            risk_manager=self.risk_manager,
            alpaca_client=session_alpaca_client,
        )

        logger.info(f"Started runner for session {session_id} (credentials: {credentials.name})")

    async def _stop_runner(self, session_id: UUID) -> None:
        """Stop the runner for a session."""
        if session_id in self.runner_manager.active_runners:
            await self.runner_manager.stop_runner(session_id)
            logger.info(f"Stopped runner for session {session_id}")

    # ===================
    # Preflight Checks
    # ===================

    async def _preflight_checks(
        self,
        tenant_id: UUID,
        credentials_id: UUID,
        mode: int,  # ExecutionMode proto value: PAPER=1, LIVE=2
    ) -> DecryptedCredentials:
        """Run all preflight checks before starting a trading session.

        Args:
            tenant_id: Tenant starting the session
            credentials_id: Alpaca credentials to use
            mode: ExecutionMode proto value (PAPER=1, LIVE=2)

        Returns:
            Decrypted credentials for use in the session

        Raises:
            ValueError: If any check fails with descriptive message
        """
        # 1. Check subscription status
        await self._check_subscription(tenant_id, mode)

        # 2. Validate credentials exist and belong to tenant
        creds = await self._get_credentials_by_id(credentials_id, tenant_id)
        if not creds:
            raise ValueError(f"Credentials {credentials_id} not found or not authorized for tenant")

        # 3. Validate credential mode matches session mode
        if mode == EXECUTION_MODE_LIVE and creds.is_paper:
            raise ValueError(
                "Cannot start LIVE session with paper trading credentials. "
                "Please use live trading credentials."
            )

        # 4. Validate Alpaca account status and buying power
        await self._check_alpaca_account(creds, mode)

        return creds

    async def _check_subscription(
        self,
        tenant_id: UUID,
        mode: int,  # ExecutionMode proto value
    ) -> None:
        """Verify tenant has active subscription for trading mode.

        Args:
            tenant_id: Tenant to check
            mode: ExecutionMode proto value (LIVE requires paid plan)

        Raises:
            ValueError: If subscription check fails
        """
        stmt = (
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .where(Subscription.status.in_(["active", "trialing"]))
            .where(Subscription.current_period_end > datetime.now(UTC))
        )
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError("No active subscription found. Please subscribe to continue trading.")

        # For LIVE trading, require paid plan (not free tier)
        if mode == EXECUTION_MODE_LIVE:
            plan = await self._get_plan(subscription.plan_id)
            if plan and plan.tier.lower() == "free":
                raise ValueError(
                    "Live trading requires a paid subscription. "
                    "Please upgrade to Starter or Pro plan."
                )

    async def _get_plan(self, plan_id: UUID) -> Plan | None:
        """Get plan by ID."""
        stmt = select(Plan).where(Plan.id == plan_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_alpaca_account(
        self,
        creds: DecryptedCredentials,
        mode: int,  # ExecutionMode proto value
    ) -> None:
        """Verify Alpaca account is active with sufficient buying power.

        Args:
            creds: Decrypted credentials to check
            mode: ExecutionMode proto value (determines minimum buying power)

        Raises:
            ValueError: If account check fails
        """
        # Create temporary client with these credentials
        client = TradingClient(
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            paper=creds.is_paper,
        )

        try:
            account = await client.get_account()
        except Exception as e:
            raise ValueError(f"Failed to connect to Alpaca with credentials '{creds.name}': {e}")
        finally:
            await client.close()

        # Check account status
        if account.status != "ACTIVE":
            raise ValueError(
                f"Alpaca account is not active (status: {account.status}). "
                "Please check your Alpaca dashboard."
            )

        # Check buying power: $0 for paper, $500 for live
        if mode == EXECUTION_MODE_LIVE and account.buying_power < 500.0:
            raise ValueError(
                f"Insufficient buying power for live trading: ${account.buying_power:.2f}. "
                f"Minimum required: $500.00"
            )

    async def _get_credentials_by_id(
        self, credentials_id: UUID, tenant_id: UUID
    ) -> DecryptedCredentials | None:
        """Fetch and decrypt credentials for a trading session.

        Direct DB query (shared database access pattern).

        Args:
            credentials_id: The credentials to fetch
            tenant_id: Tenant ID for isolation

        Returns:
            Decrypted credentials or None if not found/not authorized
        """
        stmt = (
            select(AlpacaCredentials)
            .where(AlpacaCredentials.id == credentials_id)
            .where(AlpacaCredentials.tenant_id == tenant_id)  # Tenant isolation
            .where(AlpacaCredentials.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        creds = result.scalar_one_or_none()

        if not creds:
            return None

        return DecryptedCredentials(
            id=creds.id,
            name=creds.name,
            api_key=decrypt_value(creds.api_key_encrypted),
            api_secret=decrypt_value(creds.api_secret_encrypted),
            is_paper=creds.is_paper,
        )

    def _get_strategy_sexpr(self, strategy_ver: StrategyVersion) -> str | None:
        """Extract S-expression from strategy version.

        The S-expression is stored in config_sexpr field.
        """
        # config_sexpr is the canonical storage location
        if strategy_ver.config_sexpr:
            return strategy_ver.config_sexpr

        # Fallback: Try config_json with 'sexpr' key (shouldn't happen normally)
        # config_json is typed as Mapped[dict] in SQLAlchemy model, cast to proper type
        config_json = cast(dict[str, object], strategy_ver.config_json)
        if config_json and "sexpr" in config_json:
            return str(config_json["sexpr"])

        return None


async def get_live_session_service(
    db: AsyncSession = Depends(get_db),
    runner_manager: RunnerManager = Depends(get_runner_manager),
    order_executor: OrderExecutor = Depends(get_order_executor),
    risk_manager: RiskManager = Depends(get_risk_manager),
    alpaca_client: TradingClient = Depends(get_trading_client),
) -> LiveSessionService:
    """Dependency to get live session service with runner integration."""
    return LiveSessionService(
        db=db,
        runner_manager=runner_manager,
        order_executor=order_executor,
        risk_manager=risk_manager,
        alpaca_client=alpaca_client,
    )
