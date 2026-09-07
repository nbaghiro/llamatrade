"""E2E: a fill published while the portfolio service is down must not be lost.

The fill loop is a durable Kafka consumer, which is what lets a deploy or a crash
happen mid-trading-day without dropping money events. Nothing else in the suite
tests that: every other fill is published to a service that is already up, so a
consumer that committed offsets eagerly, or subscribed from the latest offset on
restart, would still pass everywhere else and silently drop fills in production.

Here the consumer is stopped, a fill is published into its absence, and the
service is brought back. The position must appear without the fill being
republished. Restarting a container is disruptive to anything else using the
mesh, so the whole module is opt-in behind ``E2E_RESTART=1``.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Iterator

import pytest

from . import _ledger, _scaffold
from .client import MeshClient, MeshError, publish_ledger_fill

pytestmark = [pytest.mark.e2e, pytest.mark.restart]

CONTAINER = "llamatrade-portfolio"
QTY = 5
PRICE = "100"


def _docker(*args: str) -> None:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode != 0:
        pytest.fail(f"docker {' '.join(args)} failed: {result.stderr.strip()}")


def _running() -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


def _wait_serving(client: MeshClient, *, timeout: float = 120.0) -> None:
    """Block until the restarted service answers again.

    The socket is refused or reset while it comes back up, which is a different
    failure from the one under test, so it must not be read as a lost fill.
    """
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.call("portfolio", "GetPositions", {})
            return
        except (OSError, MeshError) as exc:
            last = exc
            time.sleep(2.0)
    pytest.fail(f"{CONTAINER} did not resume serving within {timeout:.0f}s (last error: {last})")


@pytest.fixture
def portfolio_restart() -> Iterator[Callable[[], None]]:
    """Stop the portfolio service; always bring it back, even on failure."""
    if not _running():
        pytest.skip(f"{CONTAINER} is not running")

    stopped = False

    def stop() -> None:
        nonlocal stopped
        _docker("stop", CONTAINER)
        stopped = True

    yield stop

    if stopped:
        _docker("start", CONTAINER)


def test_a_fill_published_while_down_is_projected_after_restart(
    throwaway_tenant: Callable[[str], MeshClient],
    demo: MeshClient,
    portfolio_restart: Callable[[], None],
) -> None:
    client = throwaway_tenant("restart")
    funded = _scaffold.fund_tenant_execution(client, demo, "Restart Resilience")
    strategy = client.call("strategy", "GetStrategy", {"strategyId": funded.strategy_id})[
        "strategy"
    ]
    symbol = strategy["symbols"][0]
    assert _ledger.position_qty(client, symbol) == 0, "this tenant should start flat"

    portfolio_restart()

    # Published into the consumer's absence: the broker must hold it.
    publish_ledger_fill(
        client.ctx["tenantId"],
        funded.account_id,
        funded.sleeve_id,
        f"e2e-restart-{funded.execution_id[:8]}",
        symbol,
        "buy",
        str(QTY),
        PRICE,
    )

    _docker("start", CONTAINER)
    _wait_serving(client)

    # The consumer resumes from its committed offset and folds the backlog.
    projected = _ledger.wait_position(client, symbol, QTY, timeout=180)
    assert projected == pytest.approx(QTY), (
        f"the fill published during downtime was never projected ({symbol} qty={projected})"
    )
