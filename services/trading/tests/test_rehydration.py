"""Tests for boot-time / periodic live-session runner rehydration (``src.recovery``).

Covers the crash-recovery invariant: a session left RUNNING/PAUSED by a dead pod
gets its in-process runner re-attached by exactly one replica (per-session
advisory lock), and a session stopped elsewhere is dropped here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src import recovery
from src.recovery import _RunnerSpec, _session_lock_key, rehydrate_pass, release_session_lease

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_leases():
    """Keep the module-global lease registry isolated per test."""
    recovery._leases.clear()
    yield
    recovery._leases.clear()


def _spec(session_id=None, paused=False) -> _RunnerSpec:
    return _RunnerSpec(
        session_id=session_id or uuid4(),
        tenant_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version=1,
        credentials_id=uuid4(),
        mode=1,
        symbols=("AAPL",),
        sleeve_id=None,
        account_id=None,
        paused=paused,
    )


def _runner_manager(running_ids=None):
    mgr = MagicMock()
    mgr.active_runners = list(running_ids or [])
    mgr.get_runner = MagicMock(return_value=None)
    mgr.stop_runner = AsyncMock()
    return mgr


def test_session_lock_key_is_stable_and_signed_64bit():
    sid = uuid4()
    assert _session_lock_key(sid) == _session_lock_key(sid)
    assert -(2**63) <= _session_lock_key(sid) < 2**63
    assert _session_lock_key(uuid4()) != _session_lock_key(sid)


async def test_release_lease_noop_when_not_held():
    # No lease for this session on this pod → must not raise.
    await release_session_lease(uuid4())


async def test_release_lease_unlocks_and_closes_when_held():
    sid = uuid4()
    conn = AsyncMock()
    recovery._leases[sid] = conn

    await release_session_lease(sid)

    conn.scalar.assert_awaited_once()  # pg_advisory_unlock
    conn.close.assert_awaited_once()
    assert sid not in recovery._leases


async def test_rehydrate_pass_claims_and_starts_unowned_session():
    spec = _spec()
    mgr = _runner_manager()

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(recovery, "_rehydrate_one", AsyncMock()) as rehydrate_one,
    ):
        started = await rehydrate_pass(mgr)

    assert started == 1
    rehydrate_one.assert_awaited_once_with(spec)


async def test_rehydrate_pass_skips_when_claim_lost_to_peer():
    spec = _spec()
    mgr = _runner_manager()

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=False)),
        patch.object(recovery, "_rehydrate_one", AsyncMock()) as rehydrate_one,
    ):
        started = await rehydrate_pass(mgr)

    assert started == 0
    rehydrate_one.assert_not_called()


async def test_rehydrate_pass_skips_session_already_running_here():
    spec = _spec()
    mgr = _runner_manager()
    mgr.get_runner = MagicMock(return_value=MagicMock())  # a runner already exists here

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)) as claim,
        patch.object(recovery, "_rehydrate_one", AsyncMock()) as rehydrate_one,
    ):
        started = await rehydrate_pass(mgr)

    assert started == 0
    claim.assert_not_called()
    rehydrate_one.assert_not_called()


async def test_rehydrate_pass_drops_lease_for_no_longer_live_session():
    dead = uuid4()
    recovery._leases[dead] = AsyncMock()
    mgr = _runner_manager(running_ids=[dead])

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(recovery, "_rehydrate_one", AsyncMock()),
    ):
        await rehydrate_pass(mgr)

    mgr.stop_runner.assert_awaited_once_with(dead)
    assert dead not in recovery._leases


async def test_rehydrate_pass_releases_lease_on_start_failure():
    spec = _spec()
    mgr = _runner_manager()

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(
            recovery, "_rehydrate_one", AsyncMock(side_effect=RuntimeError("alpaca down"))
        ),
        patch.object(recovery, "release_session_lease", AsyncMock()) as release,
    ):
        started = await rehydrate_pass(mgr)

    assert started == 0
    release.assert_awaited_once_with(spec.session_id)
