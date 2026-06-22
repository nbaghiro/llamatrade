"""Tests for health endpoint."""

from httpx import AsyncClient


async def test_health_check(client: AsyncClient):
    """Test health endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "portfolio"
    assert data["version"] == "0.1.0"


async def test_health_check_no_auth_required(client: AsyncClient):
    """Test health endpoint doesn't require authentication."""
    # Health endpoint should be accessible without auth
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_reports_ledger_runtime(client: AsyncClient):
    """Health exposes the background ledger-runtime liveness."""
    response = await client.get("/health")
    assert response.json()["ledger_runtime"] in {"ok", "degraded", "down"}


class _FakeTask:
    """Minimal asyncio.Task stand-in for the runtime-status check."""

    def __init__(self, *, done: bool = False, cancelled: bool = False, exc: object = None) -> None:
        self._done, self._cancelled, self._exc = done, cancelled, exc

    def done(self) -> bool:
        return self._done

    def cancelled(self) -> bool:
        return self._cancelled

    def exception(self) -> object:
        return self._exc


def test_ledger_runtime_status_logic() -> None:
    """down when not started, degraded when a loop crashed, ok otherwise."""
    from src.main import _ledger_runtime_status, app

    app.state.ledger_runtime_started = False
    assert _ledger_runtime_status() == "down"

    app.state.ledger_runtime_started = True
    app.state.ledger_tasks = [_FakeTask(done=False)]  # a running loop
    assert _ledger_runtime_status() == "ok"

    app.state.ledger_tasks = [_FakeTask(done=True, exc=RuntimeError("boom"))]  # crashed loop
    assert _ledger_runtime_status() == "degraded"

    app.state.ledger_tasks = [_FakeTask(done=True, cancelled=True)]  # clean shutdown
    assert _ledger_runtime_status() == "ok"


def test_ledger_runtime_degraded_on_sustained_backlog() -> None:
    """A hung active consumer (sustained fill-stream backlog) fails health so the
    liveness probe recycles the pod; a standby never fails on backlog."""
    from src.main import _ledger_runtime_status, app
    from src.tasks.fill_ingestion import FillLagTracker

    app.state.ledger_runtime_started = True
    app.state.ledger_tasks = [_FakeTask(done=False)]  # a running loop
    tracker = FillLagTracker(threshold=10, sustained_samples=1)
    app.state.fill_lag_tracker = tracker
    app.state.fill_consumer_active = True

    tracker.record(5)  # below threshold
    assert _ledger_runtime_status() == "ok"

    tracker.record(100)  # sustained backlog on the active consumer
    assert _ledger_runtime_status() == "degraded"

    app.state.fill_consumer_active = False  # a standby pod
    assert _ledger_runtime_status() == "ok"
