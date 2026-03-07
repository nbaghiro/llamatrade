# LlamaTrade Proto

Protocol Buffers definitions and generated code for LlamaTrade services.

## Structure

```
libs/proto/
├── llamatrade_proto/            # Main Python package
│   ├── __init__.py              # Re-exports clients, interceptors, server
│   │
│   ├── protos/                  # Source .proto definitions
│   │   ├── common.proto
│   │   ├── auth.proto
│   │   ├── backtest.proto
│   │   └── ...
│   │
│   ├── generated/               # Auto-generated code (from buf generate)
│   │   ├── *_pb2.py             # Protobuf message classes
│   │   ├── *_pb2_grpc.py        # gRPC service stubs
│   │   └── *_connect.py         # Connect protocol stubs
│   │
│   ├── clients/                 # Hand-written client wrappers
│   │   ├── auth.py              # AuthClient
│   │   ├── backtest.py          # BacktestClient
│   │   ├── market_data.py       # MarketDataClient
│   │   └── trading.py           # TradingClient
│   │
│   ├── interceptors/            # gRPC interceptors
│   │   ├── auth.py              # AuthInterceptor
│   │   └── logging.py           # LoggingInterceptor
│   │
│   └── server/                  # Server utilities
│       ├── base.py              # GRPCServer
│       └── connect.py           # Connect protocol helpers
│
├── buf.yaml                     # Buf module configuration
├── buf.gen.yaml                 # Code generation configuration
└── pyproject.toml               # Package definition
```

## Usage

### Generated Protocol Buffers

```python
# Import generated message classes
from llamatrade_proto.generated import auth_pb2, market_data_pb2

# Import gRPC stubs for implementing services
from llamatrade_proto.generated import auth_pb2_grpc

# Import Connect stubs for ASGI applications
from llamatrade_proto.generated.auth_connect import AuthServiceASGIApplication
```

### High-Level Client Wrappers

```python
# Import client wrappers (re-exported from package root)
from llamatrade_proto import MarketDataClient, AuthClient

# Or import directly from clients module
from llamatrade_proto.clients import MarketDataClient

# Use the client
async with MarketDataClient("market-data:8840") as client:
    bars = await client.get_historical_bars(
        symbol="AAPL",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
    )
```

### Server Utilities

```python
from llamatrade_proto import GRPCServer, LoggingInterceptor
from llamatrade_proto.generated import market_data_pb2_grpc

# Create server with interceptors
grpc_server = GRPCServer(port=8840, interceptors=[LoggingInterceptor()])

# Register servicer
grpc_server.add_servicer(
    lambda s: market_data_pb2_grpc.add_MarketDataServiceServicer_to_server(servicer, s)
)

# Start server
await grpc_server.start()
```

## Regenerating Code

After modifying `.proto` files in `llamatrade_proto/protos/`:

```bash
# From repo root
make proto

# Or from this directory
buf generate
```

The Makefile automatically fixes Python imports after generation.

## Code Generation

The `buf generate` command produces:

| Plugin | Output | Purpose |
|--------|--------|---------|
| `protocolbuffers/python` | `*_pb2.py` | Message classes |
| `grpc/python` | `*_pb2_grpc.py` | gRPC service stubs |
| `connectrpc/python` | `*_connect.py` | Connect protocol stubs |
| `mypy-protobuf` | `*_pb2.pyi` | Type stubs for mypy |
| `bufbuild/es` | `*_pb.ts` | TypeScript (in apps/web/) |

## Package Architecture

- **`llamatrade_proto`** - The main package containing protos, generated code, clients, and server utilities
