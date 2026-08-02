"""Tests for the per-session ownership lease taken on the normal start path.

A session started via ``StartSession`` must hold the same per-session advisory
lock the rehydrate pass claims before adopting a session. Without it a peer
replica sees a RUNNING row with no local runner and starts a second runner for
the same session (two runners trading one sleeve).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)

from src import recovery
from src.credentials import DecryptedCredentials
from src.models import SessionResponse
from src.recovery import _RunnerSpec, rehydrate_pass
from src.services.live_session_service import LiveSessionService
from src.services.session_service import SessionService

pytestmark = pytest.mark.asyncio

TENANT_ID = uuid4()
STRATEGY_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_leases():
    """Keep the module-global lease registry isolated per test."""
    recovery._leases.clear()
    yield
    recovery._leases.clear()


def _credentials() -> DecryptedCredentials:
    return DecryptedCredentials(
        id=uuid4(),
        name="Paper Keys",
        api_key="PKTEST12345678901234",
        api_secret="SKTEST12345678901234567890123456789012345",
        is_paper=True,
    )


def _session_response(session_id: UUID) -> SessionResponse:
    return SessionResponse(
        id=session_id,
        tenant_id=TENANT_ID,
        strategy_id=STRATEGY_ID,
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        started_at=datetime.now(UTC),
    )


def _service() -> LiveSessionService:
    """A live session service whose DB/runner/broker collaborators are mocked."""
    runner_manager = MagicMock()
    runner_manager.start_runner = AsyncMock()
    runner_manager.stop_runner = AsyncMock()
    runner_manager.get_runner = MagicMock(return_value=None)
    runner_manager.active_runners = []
    service = LiveSessionService(
        db=AsyncMock(),
        runner_manager=runner_manager,
        order_executor=MagicMock(),
        risk_manager=MagicMock(),
        alpaca_client=MagicMock(),
    )
    service._preflight_checks = AsyncMock(return_value=_credentials())
    service._resolve_ledger_identity = AsyncMock(return_value=(None, None))
    service._start_runner = AsyncMock()
    return service


async def _start(service: LiveSessionService, session_id: UUID) -> SessionResponse:
    with patch.object(
        SessionService, "start_session", AsyncMock(return_value=_session_response(session_id))
    ):
        return await service.start_session(
            tenant_id=TENANT_ID,
            user_id=uuid4(),
            strategy_id=STRATEGY_ID,
            strategy_version=1,
            name="Test Session",
            mode=EXECUTION_MODE_PAPER,
            credentials_id=uuid4(),
            symbols=["AAPL"],
        )


def _spec(session_id: UUID) -> _RunnerSpec:
    return _RunnerSpec(
        session_id=session_id,
        tenant_id=TENANT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version=1,
        credentials_id=uuid4(),
        mode=EXECUTION_MODE_PAPER,
        symbols=("AAPL",),
        sleeve_id=None,
        account_id=None,
        paused=False,
    )


def _peer_runner_manager() -> MagicMock:
    """A runner manager on another replica: it knows nothing about the session."""
    mgr = MagicMock()
    mgr.active_runners = []
    mgr.get_runner = MagicMock(return_value=None)
    mgr.stop_runner = AsyncMock()
    return mgr


async def test_start_session_claims_the_session_lease():
    session_id = uuid4()
    service = _service()

    with patch.object(recovery, "_try_claim", AsyncMock(return_value=True)) as claim:
        result = await _start(service, session_id)

    assert result.id == session_id
    claim.assert_awaited_once_with(session_id)


async def test_peer_rehydrate_pass_does_not_adopt_a_normally_started_session():
    """The key invariant: one advisory lock, two entry points, no double-run."""
    session_id = uuid4()
    service = _service()
    locks: set[UUID] = set()

    async def advisory_lock(target_id: UUID) -> bool:
        """Stand-in for pg_try_advisory_lock across replicas."""
        if target_id in locks:
            return False
        locks.add(target_id)
        return True

    with patch.object(recovery, "_try_claim", AsyncMock(side_effect=advisory_lock)):
        await _start(service, session_id)

        # A peer replica's pass sees the RUNNING row but owns no runner for it.
        with (
            patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[_spec(session_id)])),
            patch.object(recovery, "_rehydrate_one", AsyncMock()) as rehydrate_one,
        ):
            started = await rehydrate_pass(_peer_runner_manager())

    assert started == 0
    rehydrate_one.assert_not_called()


async def test_start_is_refused_when_a_peer_already_owns_the_session():
    """Losing the lock means a peer is running the session: refuse rather than double-run."""
    service = _service()

    with (
        patch.object(recovery, "_try_claim", AsyncMock(return_value=False)),
        patch.object(SessionService, "set_error", AsyncMock()),
    ):
        with pytest.raises(ValueError, match="already owned by another trading replica"):
            await _start(service, uuid4())

    service._start_runner.assert_not_called()


async def test_runner_start_failure_releases_the_lease():
    session_id = uuid4()
    service = _service()
    service._start_runner = AsyncMock(side_effect=RuntimeError("bar stream down"))

    with (
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(recovery, "release_session_lease", AsyncMock()) as release,
        patch.object(SessionService, "set_error", AsyncMock()) as set_error,
    ):
        with pytest.raises(RuntimeError, match="bar stream down"):
            await _start(service, session_id)

    release.assert_awaited_once_with(session_id)
    set_error.assert_awaited_once()


async def test_started_session_holds_then_releases_the_lease_on_stop():
    """Start takes the real lease; stop unlocks and closes its connection."""
    session_id = uuid4()
    service = _service()
    lease_conn = AsyncMock()
    lease_conn.scalar = AsyncMock(return_value=True)

    with patch.object(recovery, "_open_lease_connection", AsyncMock(return_value=lease_conn)):
        await _start(service, session_id)
        assert recovery._leases[session_id] is lease_conn

        service._get_session_by_id = AsyncMock(return_value=MagicMock())
        with patch.object(
            SessionService, "stop_session", AsyncMock(return_value=_session_response(session_id))
        ):
            await service.stop_session(session_id, TENANT_ID)

    assert session_id not in recovery._leases
    lease_conn.close.assert_awaited_once()
