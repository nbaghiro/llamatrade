"""Generated protobuf and gRPC code. Do not edit - regenerate with make proto."""

# Import proto files in dependency order to ensure proto pool is populated correctly.
# Dependency graph:
#   common -> (no deps)
#   trading -> common
#   backtest, portfolio -> common, trading
#   auth, billing, market_data, notification, strategy -> common
# fmt: off
# isort: off
from . import common_pb2 as common_pb2  # noqa: F401, E402, I001
from . import trading_pb2 as trading_pb2  # noqa: F401, E402
from . import backtest_pb2 as backtest_pb2  # noqa: F401, E402
from . import portfolio_pb2 as portfolio_pb2  # noqa: F401, E402
from . import billing_pb2 as billing_pb2  # noqa: F401, E402
from . import market_data_pb2 as market_data_pb2  # noqa: F401, E402
from . import notification_pb2 as notification_pb2  # noqa: F401, E402
from . import strategy_pb2 as strategy_pb2  # noqa: F401, E402
# isort: on
# fmt: on
