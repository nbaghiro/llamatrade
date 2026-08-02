"""Every Connect servicer must bind to its generated ASGI application.

The generated ``*_connect.py`` binds each RPC to a snake_case servicer attribute
(``function=svc.start_session``). A servicer whose methods are named otherwise
(e.g. PascalCase) type-checks and unit-tests green against hand-rolled fakes but
resolves zero endpoints against the real transport, so every request fails with
``AttributeError`` at dispatch time. This guard resolves each service's real
endpoint map against its real servicer and fails if any bound attribute is
missing, catching that class of drift after a proto regeneration.

Services share the top-level ``src`` package name, so they cannot be imported
into one interpreter side by side. Each pair is therefore checked in its own
subprocess whose working directory is the service, exactly mirroring how each
service runs in isolation in production.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


class _Pair(NamedTuple):
    """A servicer paired with the generated ASGI application that must bind it."""

    service: str
    connect_module: str
    asgi_app: str
    servicer_module: str
    servicer_class: str


# One entry per bound Connect service. Portfolio hosts two (Portfolio + Ledger).
_PAIRS: list[_Pair] = [
    _Pair(
        "agent",
        "agent_connect",
        "AgentServiceASGIApplication",
        "src.grpc.servicer",
        "AgentServicer",
    ),
    _Pair(
        "auth", "auth_connect", "AuthServiceASGIApplication", "src.grpc.servicer", "AuthServicer"
    ),
    _Pair(
        "backtest",
        "backtest_connect",
        "BacktestServiceASGIApplication",
        "src.grpc.servicer",
        "BacktestServicer",
    ),
    _Pair(
        "billing",
        "billing_connect",
        "BillingServiceASGIApplication",
        "src.grpc.servicer",
        "BillingServicer",
    ),
    _Pair(
        "market-data",
        "market_data_connect",
        "MarketDataServiceASGIApplication",
        "src.grpc.servicer",
        "MarketDataServicer",
    ),
    _Pair(
        "notification",
        "notification_connect",
        "NotificationServiceASGIApplication",
        "src.grpc.servicer",
        "NotificationServicer",
    ),
    _Pair(
        "portfolio",
        "portfolio_connect",
        "PortfolioServiceASGIApplication",
        "src.grpc.servicer",
        "PortfolioServicer",
    ),
    _Pair(
        "portfolio",
        "ledger_connect",
        "LedgerServiceASGIApplication",
        "src.grpc.ledger_servicer",
        "LedgerServicer",
    ),
    _Pair(
        "strategy",
        "strategy_connect",
        "StrategyServiceASGIApplication",
        "src.grpc.servicer",
        "StrategyServicer",
    ),
    _Pair(
        "trading",
        "trading_connect",
        "TradingServiceASGIApplication",
        "src.grpc.servicer",
        "TradingServicer",
    ),
]


_CHECK = """
from llamatrade_proto.generated.{connect_module} import {asgi_app}
from {servicer_module} import {servicer_class}

servicer = {servicer_class}()
app = {asgi_app}(servicer)
# _resolve_endpoints reproduces exactly what the transport does per request: it
# evaluates the generated endpoint map, reading each RPC's servicer attribute
# (function=svc.<snake_case>). A missing attribute raises here as it would live.
endpoints = app._resolve_endpoints(servicer)
assert endpoints, "empty endpoint map"
for path, endpoint in endpoints.items():
    fn = endpoint.function
    assert getattr(fn, "__self__", None) is servicer, f"{{path}} not bound to servicer"
print("OK", {servicer_class}.__name__, len(endpoints))
"""


@pytest.mark.parametrize("pair", _PAIRS, ids=lambda p: f"{p.service}:{p.servicer_class}")
def test_servicer_binds_to_generated_endpoints(pair: _Pair) -> None:
    """The servicer exposes every attribute its generated ASGI app binds to."""
    service_dir = _REPO_ROOT / "services" / pair.service
    assert service_dir.is_dir(), f"missing service directory: {service_dir}"

    script = _CHECK.format(
        connect_module=pair.connect_module,
        asgi_app=pair.asgi_app,
        servicer_module=pair.servicer_module,
        servicer_class=pair.servicer_class,
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=service_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, (
        f"{pair.servicer_class} does not bind to {pair.asgi_app}:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert result.stdout.startswith("OK"), result.stdout
