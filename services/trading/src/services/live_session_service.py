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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_alpaca import (
    BarStreamClient,
    TradingClient,
    TradingStreamClient,
    get_trading_client,
)
from llamatrade_compiler import SizingMode, StrategySession
from llamatrade_db import get_db
from llamatrade_db.models.billing import Plan, Subscription
from llamatrade_db.models.strategy import StrategyExecution, StrategyVersion
from llamatrade_proto.generated.billing_pb2 import PLAN_TIER_FREE
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
)

from src.clients.portfolio_client import get_portfolio_ledger_client
from src.credentials import DecryptedCredentials, resolve_credentials
from src.executor.order_executor import OrderExecutor, get_order_executor
from src.metrics import (
    record_bar_stream_reconnect,
    record_trade_stream_reconnect,
    set_bar_stream_connected,
    set_trade_stream_connected,
)
from src.models import SessionResponse
from src.risk.risk_manager import RiskManager, get_risk_manager
from src.runner.runner import RunnerConfig, RunnerManager, get_runner_manager
from src.services.session_service import SessionService
from src.streaming.publisher import get_trading_event_publisher

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
        alpaca_client: TradingClient,
    ):
        super().__init__(db)
        self.runner_manager = runner_manager
        self.order_executor = order_executor
        self.risk_manager = risk_manager
        self.alpaca_client = alpaca_client
        # The order executor's DB session is request-scoped UNLESS it is handed
        # to a runner (then the runner owns it for the session's lifetime).
        self._executor_handed_off = False

    async def aclose(self) -> None:
        """Release the request-scoped DB session (trading-hardening 13A).

        Closes this service's own session always; closes the order executor's
        session too unless it was handed to a runner (which then owns it).
        """
        import inspect

        await self.db.close()
        if not self._executor_handed_off:
            closer = getattr(self.order_executor, "aclose", None)
            if closer is not None:
                result = closer()
                if inspect.isawaitable(result):
                    await result

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
        sleeve_id: UUID | None = None,
        account_id: UUID | None = None,
        execution_id: UUID | None = None,
    ) -> SessionResponse:
        """Start a new trading session with runner.

        Creates the session in database and starts a StrategyRunner
        to execute the strategy in real-time. Ledger identity is resolved
        from the funded strategy execution when not passed explicitly —
        from ``execution_id`` when given (exact), else the strategy's most
        recently funded execution (heuristic fallback).

        Raises:
            ValueError: If preflight checks fail (subscription, credentials,
                buying power) or another active session already trades the sleeve.
        """
        # Run preflight checks BEFORE creating session
        creds = await self._preflight_checks(
            tenant_id=tenant_id,
            credentials_id=credentials_id,
            mode=mode,
        )

        # Ledger identity from the funded strategy execution (None = legacy)
        if sleeve_id is None and account_id is None:
            sleeve_id, account_id = await self._resolve_ledger_identity(
                tenant_id, strategy_id, execution_id
            )

        # One active session per sleeve: two runners sharing a sleeve would
        # race its free cash and double-trade its targets.
        if sleeve_id is not None:
            await self._ensure_sleeve_not_in_use(tenant_id, sleeve_id)

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
            sleeve_id=sleeve_id,
            account_id=account_id,
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
                sleeve_id=sleeve_id,
                account_id=account_id,
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

    async def _resolve_ledger_identity(
        self, tenant_id: UUID, strategy_id: UUID, execution_id: UUID | None = None
    ) -> tuple[UUID | None, UUID | None]:
        """(sleeve_id, account_id) of the strategy's funded execution, if any.

        The strategy service persists them on the execution when it funds a
        sleeve (CONTRACTS.md §5). An explicit ``execution_id`` resolves that
        exact execution (and fails loudly if it doesn't match the strategy). With
        no ``execution_id`` we resolve the strategy's *single* open funded
        execution; if more than one exists the binding is ambiguous and we refuse
        rather than silently guess (the old "most recent" heuristic could trade
        the wrong sleeve). (None, None) means a legacy/unfunded session.
        """
        if execution_id is not None:
            execution = await self.db.scalar(
                select(StrategyExecution).where(
                    StrategyExecution.tenant_id == tenant_id,
                    StrategyExecution.id == execution_id,
                )
            )
            if execution is None:
                raise ValueError(f"Execution {execution_id} not found")
            if execution.strategy_id != strategy_id:
                raise ValueError(f"Execution {execution_id} belongs to a different strategy")
            return execution.sleeve_id, execution.account_id

        from llamatrade_proto.generated.common_pb2 import (
            EXECUTION_STATUS_PAUSED,
            EXECUTION_STATUS_PENDING,
            EXECUTION_STATUS_RUNNING,
        )

        # Open funded executions only (a released sleeve has sleeve_id cleared);
        # limit 2 is enough to detect ambiguity.
        funded = list(
            await self.db.scalars(
                select(StrategyExecution)
                .where(
                    StrategyExecution.tenant_id == tenant_id,
                    StrategyExecution.strategy_id == strategy_id,
                    StrategyExecution.sleeve_id.is_not(None),
                    StrategyExecution.status.in_(
                        [
                            EXECUTION_STATUS_PENDING,
                            EXECUTION_STATUS_RUNNING,
                            EXECUTION_STATUS_PAUSED,
                        ]
                    ),
                )
                .order_by(StrategyExecution.created_at.desc())
                .limit(2)
            )
        )
        if not funded:
            return None, None
        if len(funded) > 1:
            raise ValueError(
                "Multiple funded executions exist for this strategy; pass an explicit "
                "execution_id to choose which sleeve this session trades."
            )
        return funded[0].sleeve_id, funded[0].account_id

    async def _ensure_sleeve_not_in_use(self, tenant_id: UUID, sleeve_id: UUID) -> None:
        """Reject a start when another live session already trades the sleeve."""
        from llamatrade_db.models.trading import TradingSession
        from llamatrade_proto.generated.common_pb2 import (
            EXECUTION_STATUS_PAUSED,
            EXECUTION_STATUS_RUNNING,
        )

        active = await self.db.scalar(
            select(TradingSession)
            .where(
                TradingSession.tenant_id == tenant_id,
                TradingSession.sleeve_id == sleeve_id,
                TradingSession.status.in_([EXECUTION_STATUS_RUNNING, EXECUTION_STATUS_PAUSED]),
            )
            .limit(1)
        )
        if active is not None:
            raise ValueError(
                f"Sleeve {sleeve_id} is already traded by session {active.id}; "
                "stop it before starting another"
            )

    async def _start_runner(
        self,
        session_id: UUID,
        tenant_id: UUID,
        strategy_id: UUID,
        version: int | None,
        symbols: list[str] | None,
        mode: int,  # ExecutionMode proto value: PAPER=1, LIVE=2
        credentials: DecryptedCredentials,
        sleeve_id: UUID | None = None,
        account_id: UUID | None = None,
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
            sleeve_id: Ledger sleeve of the funded execution (None = legacy)
            account_id: Ledger account anchoring the sleeve
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

        # Build the shared StrategySession (merged-symbol evaluation + portfolio-level
        # rebalance, identical to backtest). DRIFT sizing (resize against sleeve equity)
        # only when this session is funded (has a sleeve); otherwise BINARY.
        sleeve_aware = sleeve_id is not None
        session = StrategySession(
            strategy_sexpr,
            sizing_mode=SizingMode.DRIFT if sleeve_aware else SizingMode.BINARY,
        )

        # Create bar stream with session-specific credentials (shared lib client;
        # metrics wired via lifecycle hooks since the lib stays service-agnostic).
        bar_stream = BarStreamClient(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
            on_reconnect=record_bar_stream_reconnect,
            on_connection_change=set_bar_stream_connected,
        )

        # Create trade stream with same credentials (shared lib client; metrics
        # are wired via lifecycle hooks since the lib stays service-agnostic).
        trade_stream = TradingStreamClient(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
            on_reconnect=record_trade_stream_reconnect,
            on_connection_change=set_trade_stream_connected,
        )

        # Create Alpaca client with session-specific credentials
        session_alpaca_client = TradingClient(
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            paper=credentials.is_paper,
        )

        # Fail fast if any strategy symbol is not tradable on this account —
        # otherwise the session starts and every order for it is rejected.
        try:
            await self._check_symbols_tradable(session_alpaca_client, actual_symbols)
        except Exception:
            await session_alpaca_client.close()
            raise

        # Create runner config
        runner_config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=actual_symbols,
            timeframe=strategy_ver.timeframe or "1Min",
            warmup_bars=session.min_bars + 10,  # Extra buffer
            mode=mode,
            sleeve_id=sleeve_id,
            account_id=account_id,
        )

        # Ledger fill emission needs the Redis publisher (only for funded sessions)
        ledger_publisher = get_trading_event_publisher() if sleeve_id is not None else None

        # Sleeve state reads (equity, free cash) for sleeve-aware execution
        portfolio_client = get_portfolio_ledger_client() if sleeve_id is not None else None

        # Start the runner with session-specific client
        await self.runner_manager.start_runner(
            config=runner_config,
            strategy_fn=None,
            session=session,
            bar_stream=bar_stream,
            trade_stream=trade_stream,
            order_executor=self.order_executor,
            risk_manager=self.risk_manager,
            alpaca_client=session_alpaca_client,
            ledger_publisher=ledger_publisher,
            portfolio_client=portfolio_client,
        )
        # The runner now owns the order executor (and its DB session) for the
        # session's lifetime — don't close it when this RPC returns.
        self._executor_handed_off = True

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
            if plan and plan.tier == PLAN_TIER_FREE:
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

    async def _check_symbols_tradable(self, client: TradingClient, symbols: list[str]) -> None:
        """Reject the session if any strategy symbol is unknown or not tradable.

        A delisted or mistyped symbol would otherwise start a live session whose
        every order for it is rejected by the broker — fail fast instead.

        Raises:
            ValueError: Listing the offending symbols.
        """
        not_tradable: list[str] = []
        for symbol in symbols:
            asset = await client.get_asset(symbol)
            if asset is None or not asset.tradable:
                not_tradable.append(symbol)
        if not_tradable:
            raise ValueError(
                "Cannot start session: these symbols are not tradable on this account: "
                + ", ".join(sorted(not_tradable))
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
        return await resolve_credentials(self.db, credentials_id, tenant_id)

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


async def create_live_session_service() -> LiveSessionService:
    """Create a live session service without dependency injection.

    Used by the gRPC servicer where FastAPI DI is not available.
    """
    from llamatrade_db import get_session_maker

    from src.executor.order_executor import create_order_executor

    db = get_session_maker()()
    order_executor = await create_order_executor()
    return LiveSessionService(
        db=db,
        runner_manager=get_runner_manager(),
        order_executor=order_executor,
        risk_manager=get_risk_manager(),
        alpaca_client=get_trading_client(),
    )


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
