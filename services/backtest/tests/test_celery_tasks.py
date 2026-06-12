"""Tests for the Celery backtest task.

The task is a thin lifecycle wrapper around BacktestService.run_backtest:
these tests cover the delegation, the retry behavior for transient market
data failures (including the PENDING reset between attempts), and terminal
failure handling. Tasks run in eager mode via .apply().
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.backtest_service import MarketDataError
from src.workers import celery_tasks

BACKTEST_ID = "44444444-4444-4444-4444-444444444444"
TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def eager_celery():
    from src.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield celery_app
    celery_app.conf.task_always_eager = False


class TestRunBacktestTask:
    def test_success_delegates_to_service(self, eager_celery):
        """The task returns the service's summary on success."""
        summary = {
            "status": "completed",
            "backtest_id": BACKTEST_ID,
            "total_return": 0.12,
            "total_trades": 4,
        }

        async def fake_execute(backtest_id, tenant_id):
            assert backtest_id == BACKTEST_ID
            assert tenant_id == TENANT_ID
            return summary

        with patch.object(celery_tasks, "_execute_backtest", fake_execute):
            result = celery_tasks.run_backtest_task.apply(args=(BACKTEST_ID, TENANT_ID))

        assert result.successful()
        assert result.result == summary

    def test_market_data_error_retries_with_pending_reset(self, eager_celery):
        """Transient market-data failures reset the row to PENDING and retry.

        Regression: the old task used autoretry_for=(MarketDataError,) but the
        first failure left the row FAILED, so every retry refused to run.
        """
        attempts = []
        resets = []

        async def flaky_execute(backtest_id, tenant_id):
            attempts.append(1)
            raise MarketDataError("transient outage")

        async def record_reset(backtest_id, tenant_id):
            resets.append(backtest_id)

        with (
            patch.object(celery_tasks, "_execute_backtest", flaky_execute),
            patch.object(celery_tasks, "_reset_to_pending", record_reset),
        ):
            result = celery_tasks.run_backtest_task.apply(args=(BACKTEST_ID, TENANT_ID))

        assert not result.successful()
        # max_retries=3 → 4 attempts total
        assert len(attempts) == 4
        # The row was reset before every retry (not after the final failure)
        assert len(resets) == 3

    def test_non_market_data_error_fails_without_retry(self, eager_celery):
        """Strategy/validation errors are terminal — no retry, no reset."""
        attempts = []
        resets = []

        async def broken_execute(backtest_id, tenant_id):
            attempts.append(1)
            raise ValueError("invalid strategy")

        async def record_reset(backtest_id, tenant_id):
            resets.append(backtest_id)

        with (
            patch.object(celery_tasks, "_execute_backtest", broken_execute),
            patch.object(celery_tasks, "_reset_to_pending", record_reset),
        ):
            result = celery_tasks.run_backtest_task.apply(args=(BACKTEST_ID, TENANT_ID))

        assert not result.successful()
        assert len(attempts) == 1
        assert resets == []


class TestExecuteBacktest:
    @pytest.mark.asyncio
    async def test_execute_uses_injected_session_and_client(self, monkeypatch):
        """_execute_backtest wires session + market client into the service."""
        from contextlib import asynccontextmanager

        fake_session = AsyncMock()
        fake_client = AsyncMock()

        @asynccontextmanager
        async def fake_scope():
            yield fake_session

        monkeypatch.setattr(celery_tasks, "_session_scope", fake_scope)
        monkeypatch.setattr(celery_tasks, "_create_market_data_client", lambda: fake_client)

        captured = {}

        class FakeService:
            def __init__(self, db, market_data_client=None):
                captured["db"] = db
                captured["client"] = market_data_client

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def run_backtest(self, backtest_id, tenant_id):
                from unittest.mock import MagicMock

                response = MagicMock()
                response.metrics.total_return = 0.05
                response.metrics.total_trades = 2
                return response

        monkeypatch.setattr(celery_tasks, "BacktestService", FakeService)

        result = await celery_tasks._execute_backtest(BACKTEST_ID, TENANT_ID)

        assert captured["db"] is fake_session
        assert captured["client"] is fake_client
        assert result["status"] == "completed"
        assert result["total_trades"] == 2
