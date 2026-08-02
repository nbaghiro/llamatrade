"""Tests for boot-time / periodic live-session runner rehydration (``src.recovery``).

Covers the crash-recovery invariant: a session left RUNNING/PAUSED by a dead pod
gets its in-process runner re-attached by exactly one replica (per-session
advisory lock), and a session stopped elsewhere is dropped here.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.strategy import StrategyExecution
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)

from src import recovery
from src.recovery import (
    _ExecutionSpec,
    _orphan_specs,
    _RunnerSpec,
    _session_lock_key,
    adopt_orphaned_executions,
    rehydrate_pass,
    release_session_lease,
)

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


async def test_rehydrate_pass_evicts_dead_runner_then_reclaims():
    """A present-but-not-running runner is evicted and the session re-adopted (F13)."""
    spec = _spec()
    dead_runner = MagicMock()
    dead_runner.running = False
    mgr = _runner_manager()
    mgr.get_runner = MagicMock(return_value=dead_runner)

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(recovery, "_rehydrate_one", AsyncMock()) as rehydrate_one,
    ):
        started = await rehydrate_pass(mgr)

    assert started == 1
    mgr.stop_runner.assert_awaited_once_with(spec.session_id)  # dead runner evicted first
    rehydrate_one.assert_awaited_once_with(spec)


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


# --------------------------------------------------------------------------- #
# Orphaned RUNNING execution adoption
# --------------------------------------------------------------------------- #


def _execution(
    *,
    sleeve_id: UUID | None = None,
    credentials_id: UUID | None = None,
    age_seconds: int = 600,
) -> StrategyExecution:
    now = datetime.now(UTC)
    e = StrategyExecution(
        tenant_id=uuid4(),
        strategy_id=uuid4(),
        version=1,
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        credentials_id=credentials_id if credentials_id is not None else uuid4(),
        sleeve_id=sleeve_id if sleeve_id is not None else uuid4(),
        account_id=uuid4(),
    )
    e.id = uuid4()
    e.started_at = now - timedelta(seconds=age_seconds)
    e.created_at = now - timedelta(seconds=age_seconds)
    return e


def _exec_spec() -> _ExecutionSpec:
    return _ExecutionSpec(
        execution_id=uuid4(),
        tenant_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version=1,
        mode=EXECUTION_MODE_PAPER,
        credentials_id=uuid4(),
        user_id=uuid4(),
    )


async def test_orphan_specs_includes_stale_orphan():
    execution = _execution(age_seconds=600)
    specs = _orphan_specs([(execution, uuid4())], set(), datetime.now(UTC))
    assert len(specs) == 1
    assert specs[0].execution_id == execution.id
    assert specs[0].strategy_version == execution.version


async def test_orphan_specs_skips_execution_inside_grace_window():
    """A freshly-funded execution may still be mid-deploy — not adopted yet."""
    execution = _execution(age_seconds=10)
    assert _orphan_specs([(execution, uuid4())], set(), datetime.now(UTC)) == []


async def test_orphan_specs_skips_execution_with_live_session():
    execution = _execution(age_seconds=600)
    live = {execution.sleeve_id}
    assert _orphan_specs([(execution, uuid4())], live, datetime.now(UTC)) == []


async def test_orphan_specs_skips_execution_without_credentials():
    execution = _execution(age_seconds=600)
    execution.credentials_id = None
    assert _orphan_specs([(execution, uuid4())], set(), datetime.now(UTC)) == []


async def test_orphan_specs_naive_timestamps_are_treated_as_utc():
    execution = _execution(age_seconds=600)
    execution.started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=600)
    specs = _orphan_specs([(execution, uuid4())], set(), datetime.now(UTC))
    assert len(specs) == 1


async def test_adopt_starts_session_and_leases_it():
    spec = _exec_spec()
    new_session_id = uuid4()

    with (
        patch.object(recovery, "_load_orphaned_executions", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)) as claim,
        patch.object(recovery, "_adopt_one", AsyncMock(return_value=new_session_id)) as adopt,
    ):
        adopted = await adopt_orphaned_executions()

    assert adopted == 1
    adopt.assert_awaited_once_with(spec)
    # Execution lock claimed first, then the new session's lease taken over.
    assert [c.args[0] for c in claim.await_args_list] == [spec.execution_id, new_session_id]


async def test_adopt_exactly_once_under_concurrent_passes():
    """Two racing passes adopt one orphan exactly once (advisory-lock arbitration)."""
    spec = _exec_spec()
    claimed: set[UUID] = set()

    async def fake_claim(target_id: UUID) -> bool:
        if target_id in claimed:
            return False
        claimed.add(target_id)
        return True

    with (
        patch.object(recovery, "_load_orphaned_executions", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(side_effect=fake_claim)),
        patch.object(recovery, "release_session_lease", AsyncMock()),
        patch.object(recovery, "_adopt_one", AsyncMock(return_value=uuid4())) as adopt,
    ):
        results = await asyncio.gather(adopt_orphaned_executions(), adopt_orphaned_executions())

    assert sum(results) == 1
    adopt.assert_awaited_once()


async def test_adopt_skips_when_claim_lost_to_peer():
    spec = _exec_spec()

    with (
        patch.object(recovery, "_load_orphaned_executions", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=False)),
        patch.object(recovery, "_adopt_one", AsyncMock()) as adopt,
    ):
        adopted = await adopt_orphaned_executions()

    assert adopted == 0
    adopt.assert_not_called()


async def test_adopt_skips_when_lease_already_held_here():
    spec = _exec_spec()
    recovery._leases[spec.execution_id] = AsyncMock()

    with (
        patch.object(recovery, "_load_orphaned_executions", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)) as claim,
        patch.object(recovery, "_adopt_one", AsyncMock()) as adopt,
    ):
        adopted = await adopt_orphaned_executions()

    assert adopted == 0
    claim.assert_not_called()
    adopt.assert_not_called()


async def test_adopt_failure_releases_lock_and_does_not_raise():
    spec = _exec_spec()

    with (
        patch.object(recovery, "_load_orphaned_executions", AsyncMock(return_value=[spec])),
        patch.object(recovery, "_try_claim", AsyncMock(return_value=True)),
        patch.object(recovery, "_adopt_one", AsyncMock(side_effect=RuntimeError("start failed"))),
        patch.object(recovery, "release_session_lease", AsyncMock()) as release,
    ):
        adopted = await adopt_orphaned_executions()

    assert adopted == 0
    release.assert_awaited_once_with(spec.execution_id)


# --------------------------------------------------------------------------- #
# Lease integrity: the heartbeat and the re-verified claim
# --------------------------------------------------------------------------- #


def _lease_conn(*, holds: bool, raises: bool = False) -> AsyncMock:
    """A lease connection whose ``pg_locks`` probe is scripted."""
    conn = AsyncMock()
    conn.scalar = AsyncMock(side_effect=RuntimeError("torn") if raises else None)
    if not raises:
        conn.scalar.return_value = holds
    return conn


async def test_claim_re_verifies_a_registered_lease_before_trusting_it():
    """A registry entry is only as good as its connection: the claim asks."""
    sid = uuid4()
    conn = _lease_conn(holds=True)
    recovery._leases[sid] = conn

    assert await recovery._try_claim(sid) is True
    conn.scalar.assert_awaited_once()  # the probe, not a cache hit
    assert recovery._leases[sid] is conn


async def test_claim_drops_a_torn_lease_and_re_acquires_for_real():
    """A torn holder must go back to Postgres rather than answer from memory."""
    sid = uuid4()
    torn = _lease_conn(holds=False)
    fresh = _lease_conn(holds=True)
    recovery._leases[sid] = torn

    with patch.object(recovery, "_open_lease_connection", AsyncMock(return_value=fresh)):
        assert await recovery._try_claim(sid) is True

    assert recovery._leases[sid] is fresh
    torn.close.assert_awaited_once()


async def test_claim_is_refused_when_a_peer_took_the_torn_lease():
    sid = uuid4()
    torn = _lease_conn(holds=False)
    peer_held = _lease_conn(holds=False)  # pg_try_advisory_lock returns false
    recovery._leases[sid] = torn

    with patch.object(recovery, "_open_lease_connection", AsyncMock(return_value=peer_held)):
        assert await recovery._try_claim(sid) is False

    assert sid not in recovery._leases
    peer_held.close.assert_awaited_once()


async def test_heartbeat_stops_the_runner_of_a_dead_lease_and_keeps_live_ones():
    """A pod that lost its lease must not keep trading — the peer's adoption is
    the recovery path, so the local runner is stopped fail-safe."""
    dead, live = uuid4(), uuid4()
    recovery._leases[dead] = _lease_conn(holds=False, raises=True)
    recovery._leases[live] = _lease_conn(holds=True)
    mgr = _runner_manager(running_ids=[dead, live])

    lost = await recovery.sweep_dead_leases(mgr)

    assert lost == [dead]
    assert dead not in recovery._leases
    assert live in recovery._leases
    mgr.stop_runner.assert_awaited_once_with(dead)


async def test_rehydrate_pass_heartbeats_the_leases_first():
    """The heartbeat rides the periodic pass — nothing else touches the lease
    connection between claims."""
    dead = uuid4()
    recovery._leases[dead] = _lease_conn(holds=False)
    mgr = _runner_manager(running_ids=[dead])

    with (
        patch.object(recovery, "_load_live_specs", AsyncMock(return_value=[])),
        patch.object(recovery, "_rehydrate_one", AsyncMock()),
    ):
        await rehydrate_pass(mgr)

    assert dead not in recovery._leases
    mgr.stop_runner.assert_awaited_once_with(dead)
