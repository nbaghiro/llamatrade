"""Live session service - session management with runner lifecycle integration.

Extends SessionService to integrate with StrategyRunner for live trading.
When sessions start, runners start. When sessions stop, runners stop.
"""

import logging
from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.strategy import StrategyVersion
from sqlalchemy.ext.asyncio import AsyncSession

from src.alpaca_client import AlpacaTradingClient, get_alpaca_trading_client
from src.compiler_adapter import StrategyAdapter
from src.executor.order_executor import OrderExecutor, get_order_executor
from src.models import SessionResponse, TradingMode
from src.risk.risk_manager import RiskManager, get_risk_manager
from src.runner.bar_stream import AlpacaBarStream, StreamConfig
from src.runner.runner import RunnerConfig, RunnerManager, get_runner_manager
from src.services.session_service import SessionService

logger = logging.getLogger(__name__)


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
        alpaca_client: AlpacaTradingClient,
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
        mode: TradingMode,
        credentials_id: UUID,
        symbols: list[str] | None = None,
        config: dict | None = None,
    ) -> SessionResponse:
        """Start a new trading session with runner.

        Creates the session in database and starts a StrategyRunner
        to execute the strategy in real-time.
        """
        # Create session in database first
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
        mode: TradingMode,
    ) -> None:
        """Create and start a runner for the session."""
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

        # Create bar stream
        # Note: In production, we'd get API credentials from the credentials store
        bar_stream = AlpacaBarStream(
            StreamConfig(
                api_key=self.alpaca_client.api_key,
                api_secret=self.alpaca_client.api_secret,
                paper=(mode == TradingMode.PAPER),
            )
        )

        # Create runner config
        runner_config = RunnerConfig(
            tenant_id=tenant_id,
            deployment_id=session_id,
            strategy_id=strategy_id,
            symbols=actual_symbols,
            timeframe=strategy_ver.timeframe or "1Min",
            warmup_bars=strategy_fn.min_bars + 10,  # Extra buffer
        )

        # Start the runner
        await self.runner_manager.start_runner(
            config=runner_config,
            strategy_fn=strategy_fn,
            bar_stream=bar_stream,
            order_executor=self.order_executor,
            risk_manager=self.risk_manager,
            alpaca_client=self.alpaca_client,
        )

        logger.info(f"Started runner for session {session_id}")

    async def _stop_runner(self, session_id: UUID) -> None:
        """Stop the runner for a session."""
        if session_id in self.runner_manager.active_runners:
            await self.runner_manager.stop_runner(session_id)
            logger.info(f"Stopped runner for session {session_id}")

    def _get_strategy_sexpr(self, strategy_ver: StrategyVersion) -> str | None:
        """Extract S-expression from strategy version.

        The S-expression could be stored in different ways depending
        on the strategy format.
        """
        # Try definition_sexpr field
        if hasattr(strategy_ver, "definition_sexpr") and strategy_ver.definition_sexpr:
            sexpr: str = str(strategy_ver.definition_sexpr)
            return sexpr

        # Try definition JSON with 'sexpr' key
        if strategy_ver.definition and isinstance(strategy_ver.definition, dict):
            if "sexpr" in strategy_ver.definition:
                sexpr_value: str = str(strategy_ver.definition["sexpr"])
                return sexpr_value

        # Try to serialize from AST if available
        # (would need DSL serializer)

        return None


async def get_live_session_service(
    db: AsyncSession = Depends(get_db),
    runner_manager: RunnerManager = Depends(get_runner_manager),
    order_executor: OrderExecutor = Depends(get_order_executor),
    risk_manager: RiskManager = Depends(get_risk_manager),
    alpaca_client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
) -> LiveSessionService:
    """Dependency to get live session service with runner integration."""
    return LiveSessionService(
        db=db,
        runner_manager=runner_manager,
        order_executor=order_executor,
        risk_manager=risk_manager,
        alpaca_client=alpaca_client,
    )
