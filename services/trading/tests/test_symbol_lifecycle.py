"""Tests for symbol lifecycle handling in live sessions.

Three surfaces:
  1. start-time preflight refuses a session whose symbols are not both active
     and tradable at the broker;
  2. the runner reports a stalled evaluation gate (bars stopped arriving) once
     per stall episode;
  3. an asset that stops being tradable mid-session marks the session degraded
     and asks the user to decide, without closing anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_alpaca import Asset, MockBarStream, MockTradeStream
from llamatrade_alpaca import StreamBar as BarData
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)
from llamatrade_runtime import StrategySession

from src.credentials import DecryptedCredentials
from src.models import SESSION_DEGRADED_KEY
from src.runner.runner import RunnerConfig, StrategyRunner
from src.services.live_session_service import LiveSessionService
from src.services.session_service import SessionService
from src.symbol_status import asset_halt_reason

STRATEGY = (
    '(strategy "Two Symbol" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)


def _asset(symbol: str, *, status: str = "active", tradable: bool = True) -> Asset:
    return Asset(id=uuid4().hex, symbol=symbol, status=status, tradable=tradable)


# --------------------------------------------------------------------------- #
# Halt classification
# --------------------------------------------------------------------------- #


def test_asset_halt_reason_classifies_each_state():
    assert asset_halt_reason(_asset("SPY")) is None
    assert asset_halt_reason(None) == "unknown"
    assert asset_halt_reason(_asset("SPY", status="inactive")) == "inactive"
    assert asset_halt_reason(_asset("SPY", tradable=False)) == "not_tradable"


# --------------------------------------------------------------------------- #
# Start-time preflight
# --------------------------------------------------------------------------- #


def _live_service() -> LiveSessionService:
    runner_manager = MagicMock()
    runner_manager.start_runner = AsyncMock()
    return LiveSessionService(
        db=AsyncMock(),
        runner_manager=runner_manager,
        order_executor=MagicMock(),
        risk_manager=MagicMock(),
        alpaca_client=MagicMock(),
    )


def _broker(**assets: Asset | None) -> MagicMock:
    client = MagicMock()
    client.get_asset = AsyncMock(side_effect=lambda symbol: assets.get(symbol))
    client.close = AsyncMock()
    return client


class TestPreflightSymbolCheck:
    """Every subscribed symbol must be active and tradable before a session starts."""

    async def test_all_active_and_tradable_passes(self):
        service = _live_service()
        client = _broker(SPY=_asset("SPY"), TLT=_asset("TLT"))

        await service._check_symbols_tradable(client, ["SPY", "TLT"])

    async def test_inactive_symbol_is_refused(self):
        service = _live_service()
        client = _broker(SPY=_asset("SPY"), XYZ=_asset("XYZ", status="inactive"))

        with pytest.raises(ValueError, match=r"XYZ \(no longer active"):
            await service._check_symbols_tradable(client, ["SPY", "XYZ"])

    async def test_non_tradable_symbol_is_refused(self):
        service = _live_service()
        client = _broker(SPY=_asset("SPY"), XYZ=_asset("XYZ", tradable=False))

        with pytest.raises(ValueError, match=r"XYZ \(not tradable"):
            await service._check_symbols_tradable(client, ["SPY", "XYZ"])

    async def test_unknown_symbol_is_refused(self):
        service = _live_service()
        client = _broker(SPY=_asset("SPY"))

        with pytest.raises(ValueError, match=r"NOPE \(unknown"):
            await service._check_symbols_tradable(client, ["SPY", "NOPE"])

    async def test_preflight_runs_the_symbol_check_with_session_credentials(self):
        service = _live_service()
        service._check_subscription = AsyncMock()
        service._check_alpaca_account = AsyncMock()
        creds = DecryptedCredentials(
            id=uuid4(),
            name="Paper Keys",
            api_key="PKTEST12345678901234",
            api_secret="SKTEST12345678901234567890123456789012345",
            is_paper=True,
        )
        service._get_credentials_by_id = AsyncMock(return_value=creds)
        client = _broker(XYZ=_asset("XYZ", status="inactive"))

        with patch("src.services.live_session_service.build_trading_client", return_value=client):
            with pytest.raises(ValueError, match="XYZ"):
                await service._preflight_checks(
                    tenant_id=uuid4(),
                    credentials_id=uuid4(),
                    mode=EXECUTION_MODE_PAPER,
                    symbols=["XYZ"],
                )

        client.close.assert_awaited_once()

    async def test_untradable_symbol_prevents_session_creation(self):
        """The refusal lands before any session row exists."""
        service = _live_service()
        service._resolve_symbols = AsyncMock(return_value=["XYZ"])
        service._preflight_checks = AsyncMock(side_effect=ValueError("not tradable: XYZ"))

        with patch.object(SessionService, "start_session", AsyncMock()) as create_row:
            with pytest.raises(ValueError, match="XYZ"):
                await service.start_session(
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                    strategy_id=uuid4(),
                    strategy_version=1,
                    name="Test Session",
                    mode=EXECUTION_MODE_PAPER,
                    credentials_id=uuid4(),
                    symbols=["XYZ"],
                )

        create_row.assert_not_called()


# --------------------------------------------------------------------------- #
# Runner: evaluation-gate stall
# --------------------------------------------------------------------------- #


def _runner(*, symbols: list[str] | None = None, stall_seconds: int = 300) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=symbols or ["SPY", "TLT"],
        timeframe="1Min",
        warmup_bars=5,
        enforce_trading_hours=False,
        evaluation_stall_seconds=stall_seconds,
    )
    order_executor = AsyncMock()
    order_executor.submit_order.return_value = MagicMock(
        id=uuid4(), status="submitted", client_order_id="lt-test"
    )
    risk_manager = AsyncMock()
    risk_manager.check_order.return_value = MagicMock(passed=True, violations=[])
    runner = StrategyRunner(
        config=config,
        strategy_fn=None,
        bar_stream=MockBarStream(bars={s: [] for s in (symbols or ["SPY", "TLT"])}),
        trade_stream=MockTradeStream(),
        order_executor=order_executor,
        risk_manager=risk_manager,
        alert_service=AsyncMock(),
        session=StrategySession(STRATEGY),
    )
    runner._last_gate_open_at = datetime.now(UTC)
    return runner


def _bar(symbol: str, ts: datetime, close: float = 100.0) -> BarData:
    return BarData(
        symbol=symbol, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000
    )


class TestEvaluationStall:
    """A symbol whose bars stop arriving freezes the strategy — report it once."""

    async def test_no_alert_inside_the_staleness_window(self):
        runner = _runner()
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=10)

        await runner._check_evaluation_stall(["TLT"])

        runner.alerts.on_evaluation_stalled.assert_not_called()

    async def test_alerts_once_per_stall_episode(self):
        runner = _runner(stall_seconds=60)
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=120)

        with patch("src.runner.runner.record_evaluation_stall") as record:
            await runner._check_evaluation_stall(["TLT"])
            await runner._check_evaluation_stall(["TLT"])
            await runner._check_evaluation_stall(["TLT"])

        assert record.call_count == 1
        runner.alerts.on_evaluation_stalled.assert_awaited_once()
        kwargs = runner.alerts.on_evaluation_stalled.await_args.kwargs
        assert kwargs["symbols"] == ["TLT"]
        assert kwargs["stale_seconds"] >= 120
        assert kwargs["tenant_id"] == runner.config.tenant_id

    async def test_a_new_episode_alerts_again_after_recovery(self):
        runner = _runner(stall_seconds=60)
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=120)

        await runner._check_evaluation_stall(["TLT"])
        runner._note_gate_open()  # bars resumed
        assert runner._stall_alerted is False
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=120)
        await runner._check_evaluation_stall(["TLT"])

        assert runner.alerts.on_evaluation_stalled.await_count == 2

    async def test_incomplete_bar_set_triggers_the_check(self):
        """The gate stays shut while TLT has no bar for the period."""
        runner = _runner(stall_seconds=60)
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=120)

        await runner._process_bar(_bar("SPY", datetime(2024, 1, 1, 14, 30, tzinfo=UTC)))

        assert runner._last_evaluated_ts is None
        runner.alerts.on_evaluation_stalled.assert_awaited_once()
        assert runner.alerts.on_evaluation_stalled.await_args.kwargs["symbols"] == ["TLT"]

    async def test_complete_bar_set_reopens_the_gate(self):
        runner = _runner(stall_seconds=60)
        runner._stall_alerted = True
        ts = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)

        await runner._process_bar(_bar("SPY", ts))
        await runner._process_bar(_bar("TLT", ts, close=50.0))

        assert runner._stall_alerted is False
        assert runner._last_evaluated_ts == ts

    async def test_paused_session_is_not_a_stall(self):
        runner = _runner(stall_seconds=60)
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=600)
        runner.pause()

        await runner._check_evaluation_stall(["TLT"])

        runner.alerts.on_evaluation_stalled.assert_not_called()

    async def test_closed_market_is_not_a_stall(self):
        runner = _runner(stall_seconds=60)
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=600)
        runner._trading_hours = MagicMock()
        runner._trading_hours.is_market_open = MagicMock(return_value=False)

        await runner._check_evaluation_stall(["TLT"])

        runner.alerts.on_evaluation_stalled.assert_not_called()

    def test_stalled_symbols_reports_the_lagging_symbol(self):
        runner = _runner()
        ts = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
        runner._latest_ts = {"SPY": ts, "TLT": ts - timedelta(minutes=5)}

        assert runner._stalled_symbols() == ["TLT"]

    def test_stalled_symbols_reports_all_when_the_whole_feed_is_stale(self):
        runner = _runner()
        ts = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
        runner._latest_ts = {"SPY": ts, "TLT": ts}

        assert runner._stalled_symbols() == ["SPY", "TLT"]

    def test_stalled_symbols_reports_all_before_any_bar_arrives(self):
        runner = _runner()

        assert runner._stalled_symbols() == ["SPY", "TLT"]

    def test_runtime_loop_bar_storage_keeps_the_gate_bookkeeping(self):
        """The runtime feed path records gate opens too, so the periodic check works there."""
        runner = _runner()
        runner._stall_alerted = True
        ts = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)

        runner._store_live_bar(_bar("SPY", ts))
        assert runner._stall_alerted is True  # TLT still missing
        runner._store_live_bar(_bar("TLT", ts, close=50.0))

        assert runner._stall_alerted is False
        assert runner._stalled_symbols() == ["SPY", "TLT"]  # both current

    async def test_legacy_per_symbol_runner_never_reports_a_stall(self):
        """Without the merged-symbol session there is no all-symbols gate to watch."""
        runner = _runner()
        runner._session = None
        runner._last_gate_open_at = datetime.now(UTC) - timedelta(seconds=600)

        await runner._check_evaluation_stall(["TLT"])

        runner.alerts.on_evaluation_stalled.assert_not_called()


# --------------------------------------------------------------------------- #
# Runner: delisting mid-session
# --------------------------------------------------------------------------- #


class _FakeDB:
    """Minimal async session stand-in for the degraded-marker write."""

    def __init__(self, session: TradingSession | None) -> None:
        self._session = session
        self.committed = False

    async def __aenter__(self) -> _FakeDB:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def scalar(self, statement: object) -> TradingSession | None:
        return self._session

    async def commit(self) -> None:
        self.committed = True


def _session_row(runner: StrategyRunner) -> TradingSession:
    row = TradingSession(
        tenant_id=runner.config.tenant_id,
        strategy_id=runner.config.strategy_id,
        strategy_version=1,
        credentials_id=uuid4(),
        name="Test Session",
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        config={},
        symbols=list(runner.config.symbols),
        created_by=uuid4(),
    )
    row.id = runner.config.execution_id
    row.started_at = datetime.now(UTC)
    row.stopped_at = None
    row.sleeve_id = None
    row.account_id = None
    return row


class TestSymbolLifecycleDuringOperation:
    """A delisted holding is flagged for a user decision, never auto-liquidated."""

    @staticmethod
    def _client(**assets: Asset | None) -> MagicMock:
        client = MagicMock()
        client.get_asset = AsyncMock(side_effect=lambda symbol: assets.get(symbol))
        client.close_position = AsyncMock()
        return client

    async def test_delisted_symbol_marks_degraded_and_alerts_without_closing(self):
        runner = _runner()
        runner.alpaca_client = self._client(SPY=_asset("SPY"), TLT=_asset("TLT", status="inactive"))
        row = _session_row(runner)
        db = _FakeDB(row)

        with (
            patch("llamatrade_db.get_session_maker", return_value=lambda: db),
            patch("llamatrade_db.session.bind_tenant_guc"),
            patch("src.runner.runner.record_symbol_halt") as record,
        ):
            await runner._check_symbol_lifecycle()

        record.assert_called_once_with("inactive")
        assert runner._halted_symbols == {"TLT"}
        assert db.committed is True
        marker = row.config[SESSION_DEGRADED_KEY]
        assert marker["reason"] == "inactive"
        assert marker["symbols"] == ["TLT"]

        runner.alerts.on_symbol_not_tradable.assert_awaited_once()
        kwargs = runner.alerts.on_symbol_not_tradable.await_args.kwargs
        assert kwargs["symbol"] == "TLT"
        assert kwargs["reason"] == "inactive"
        # No forced liquidation: the decision stays with the user.
        runner.alpaca_client.close_position.assert_not_called()

    async def test_each_halted_symbol_reports_once(self):
        runner = _runner()
        runner.alpaca_client = self._client(SPY=_asset("SPY"), TLT=_asset("TLT", tradable=False))

        with (
            patch("llamatrade_db.get_session_maker", return_value=lambda: _FakeDB(None)),
            patch("llamatrade_db.session.bind_tenant_guc"),
            patch("src.runner.runner.record_symbol_halt") as record,
        ):
            await runner._check_symbol_lifecycle()
            await runner._check_symbol_lifecycle()

        assert record.call_count == 1
        assert runner.alerts.on_symbol_not_tradable.await_count == 1

    async def test_all_tradable_symbols_are_left_alone(self):
        runner = _runner()
        runner.alpaca_client = self._client(SPY=_asset("SPY"), TLT=_asset("TLT"))

        with patch("src.runner.runner.record_symbol_halt") as record:
            await runner._check_symbol_lifecycle()

        record.assert_not_called()
        runner.alerts.on_symbol_not_tradable.assert_not_called()
        assert runner._halted_symbols == set()

    async def test_asset_lookup_failure_does_not_flag_the_symbol(self):
        """A broker hiccup must not degrade a healthy session."""
        runner = _runner()
        client = MagicMock()
        client.get_asset = AsyncMock(side_effect=RuntimeError("alpaca down"))
        runner.alpaca_client = client

        await runner._check_symbol_lifecycle()

        assert runner._halted_symbols == set()
        runner.alerts.on_symbol_not_tradable.assert_not_called()

    async def test_marker_write_failure_is_not_fatal(self):
        runner = _runner()
        runner.alpaca_client = self._client(SPY=_asset("SPY"), TLT=_asset("TLT", status="inactive"))

        with patch("llamatrade_db.get_session_maker", side_effect=RuntimeError("no pool")):
            await runner._check_symbol_lifecycle()

        runner.alerts.on_symbol_not_tradable.assert_awaited_once()

    async def test_degraded_marker_is_surfaced_on_session_reads(self):
        runner = _runner()
        runner.alpaca_client = self._client(SPY=_asset("SPY"), TLT=_asset("TLT", status="inactive"))
        row = _session_row(runner)

        with (
            patch("llamatrade_db.get_session_maker", return_value=lambda: _FakeDB(row)),
            patch("llamatrade_db.session.bind_tenant_guc"),
        ):
            await runner._check_symbol_lifecycle()

        service = SessionService(db=AsyncMock())
        response = service._to_response(row)

        assert response.degraded is not None
        assert response.degraded.reason == "inactive"
        assert response.degraded.symbols == ["TLT"]

    def test_no_marker_means_no_degradation_on_reads(self):
        service = SessionService(db=AsyncMock())
        row = TradingSession(
            tenant_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version=1,
            credentials_id=uuid4(),
            name="Test Session",
            mode=EXECUTION_MODE_PAPER,
            status=EXECUTION_STATUS_RUNNING,
            config={},
            symbols=["SPY"],
            created_by=uuid4(),
        )
        row.id = uuid4()
        row.started_at = datetime.now(UTC)
        row.sleeve_id = None
        row.account_id = None
        row.stopped_at = None

        assert service._to_response(row).degraded is None

    def test_unreadable_marker_is_ignored_on_reads(self):
        service = SessionService(db=AsyncMock())
        row = TradingSession(
            tenant_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version=1,
            credentials_id=uuid4(),
            name="Test Session",
            mode=EXECUTION_MODE_PAPER,
            status=EXECUTION_STATUS_RUNNING,
            config={SESSION_DEGRADED_KEY: {"unexpected": Decimal("1")}},
            symbols=["SPY"],
            created_by=uuid4(),
        )
        row.id = uuid4()
        row.started_at = datetime.now(UTC)
        row.sleeve_id = None
        row.account_id = None
        row.stopped_at = None

        assert service._to_response(row).degraded is None
