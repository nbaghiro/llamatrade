"""LlamaTrade v1 Protocol Buffers and Connect stubs."""

# Re-export all proto modules for convenience
# IMPORTANT: Import order matters due to protobuf dependencies:
# 1. common_pb2 - base types, no dependencies
# 2. trading_pb2 - depends on common_pb2
# 3. backtest_pb2 - depends on common_pb2 AND trading_pb2
# 4. Everything else - depends only on common_pb2

# isort: off
# ruff: noqa: I001, E402

# Base types first (no dependencies)
from . import common_pb2  # noqa: E402

# trading_pb2 depends on common_pb2
from . import trading_pb2  # noqa: E402

# backtest_pb2 depends on common_pb2 AND trading_pb2
from . import backtest_pb2  # noqa: E402

# Remaining protobuf modules (depend only on common_pb2)
from . import auth_pb2  # noqa: E402
from . import billing_pb2  # noqa: E402
from . import market_data_pb2  # noqa: E402
from . import notification_pb2  # noqa: E402
from . import portfolio_pb2  # noqa: E402
from . import strategy_pb2  # noqa: E402

# Connect service modules (depend on pb2 modules)
from . import auth_connect  # noqa: E402
from . import backtest_connect  # noqa: E402
from . import billing_connect  # noqa: E402
from . import market_data_connect  # noqa: E402
from . import notification_connect  # noqa: E402
from . import portfolio_connect  # noqa: E402
from . import strategy_connect  # noqa: E402
from . import trading_connect  # noqa: E402

# isort: on

__all__ = [
    # Protobuf message modules
    "common_pb2",
    "auth_pb2",
    "backtest_pb2",
    "billing_pb2",
    "market_data_pb2",
    "notification_pb2",
    "portfolio_pb2",
    "strategy_pb2",
    "trading_pb2",
    # Connect service modules
    "auth_connect",
    "backtest_connect",
    "billing_connect",
    "market_data_connect",
    "notification_connect",
    "portfolio_connect",
    "strategy_connect",
    "trading_connect",
]
