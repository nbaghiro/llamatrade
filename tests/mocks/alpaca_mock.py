"""Alpaca Markets API mock server.

This mock server simulates the Alpaca Markets API for integration testing.
It provides endpoints for:
- Market data (bars, quotes, trades)
- Trading (orders, positions)
- Account information

Usage:
    # Start the mock server
    uvicorn tests.mocks.alpaca_mock:app --port 8888

    # Or use as fixture in tests
    from tests.mocks import create_alpaca_mock_server
    with create_alpaca_mock_server() as server:
        # Tests use server.base_url
        pass
"""

import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(
    title="Alpaca Mock API",
    description="Mock Alpaca Markets API for testing",
    version="2.0.0",
)

# ==========================================
# In-memory data stores
# ==========================================


@dataclass
class MockDataStore:
    """In-memory storage for mock data."""

    bars: dict[str, list[dict]] = field(default_factory=dict)
    orders: dict[str, dict] = field(default_factory=dict)
    positions: dict[str, dict] = field(default_factory=dict)
    account: dict = field(default_factory=dict)

    def __post_init__(self):
        # Initialize default account
        self.account = {
            "id": str(uuid4()),
            "account_number": "PA1234567890",
            "status": "ACTIVE",
            "currency": "USD",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "buying_power": "200000.00",
            "equity": "100000.00",
            "last_equity": "99500.00",
            "pattern_day_trader": False,
            "trading_blocked": False,
            "transfers_blocked": False,
            "account_blocked": False,
        }

        # Initialize some sample bars
        self._generate_sample_bars()

    def _generate_sample_bars(self):
        """Generate sample bar data for common symbols."""
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        base_prices = {"AAPL": 175, "GOOGL": 140, "MSFT": 380, "AMZN": 175, "TSLA": 250}

        for symbol in symbols:
            self.bars[symbol] = []
            base_price = base_prices.get(symbol, 100)

            # Generate 30 days of daily bars
            for i in range(30):
                date = datetime.now(UTC) - timedelta(days=30 - i)
                # Add some price variation
                variation = (i % 5 - 2) * 0.01
                price = base_price * (1 + variation)

                self.bars[symbol].append(
                    {
                        "t": date.isoformat(),
                        "o": round(price * 0.99, 2),
                        "h": round(price * 1.02, 2),
                        "l": round(price * 0.98, 2),
                        "c": round(price, 2),
                        "v": 10000000 + i * 100000,
                        "n": 50000 + i * 1000,
                        "vw": round(price, 2),
                    }
                )


# Global data store
store = MockDataStore()


# ==========================================
# Pydantic models
# ==========================================


class OrderRequest(BaseModel):
    """Order creation request."""

    symbol: str
    qty: float | None = None
    notional: float | None = None
    side: str  # buy, sell
    type: str  # market, limit, stop, stop_limit
    time_in_force: str = "day"
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None


class SetBarsRequest(BaseModel):
    """Request to set mock bar data."""

    symbol: str
    bars: list[dict[str, Any]]


# ==========================================
# Market Data endpoints
# ==========================================


@app.get("/v2/stocks/{symbol}/bars")
async def get_stock_bars(
    symbol: str,
    timeframe: str = Query("1Day"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(1000),
    adjustment: str = Query("raw"),
    feed: str = Query("sip"),
):
    """Get historical bars for a symbol."""
    symbol = symbol.upper()

    if symbol not in store.bars:
        # Return empty result for unknown symbols
        return {"bars": {symbol: []}, "next_page_token": None, "symbol": symbol}

    bars = store.bars[symbol]

    # Apply limit
    bars = bars[-limit:] if len(bars) > limit else bars

    return {
        "bars": {symbol: bars},
        "next_page_token": None,
        "symbol": symbol,
    }


@app.get("/v2/stocks/bars")
async def get_multi_bars(
    symbols: str = Query(...),
    timeframe: str = Query("1Day"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(1000),
):
    """Get historical bars for multiple symbols."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    result = {}
    for symbol in symbol_list:
        if symbol in store.bars:
            bars = store.bars[symbol]
            result[symbol] = bars[-limit:] if len(bars) > limit else bars
        else:
            result[symbol] = []

    return {"bars": result, "next_page_token": None}


@app.get("/v2/stocks/{symbol}/quotes/latest")
async def get_latest_quote(symbol: str):
    """Get the latest quote for a symbol."""
    symbol = symbol.upper()

    if symbol not in store.bars or not store.bars[symbol]:
        raise HTTPException(status_code=404, detail="Symbol not found")

    latest_bar = store.bars[symbol][-1]
    price = latest_bar["c"]

    return {
        "symbol": symbol,
        "quote": {
            "t": datetime.now(UTC).isoformat(),
            "ax": "V",
            "ap": round(price * 1.001, 2),
            "as": 100,
            "bx": "V",
            "bp": round(price * 0.999, 2),
            "bs": 100,
            "c": ["R"],
            "z": "A",
        },
    }


@app.get("/v2/stocks/{symbol}/trades/latest")
async def get_latest_trade(symbol: str):
    """Get the latest trade for a symbol."""
    symbol = symbol.upper()

    if symbol not in store.bars or not store.bars[symbol]:
        raise HTTPException(status_code=404, detail="Symbol not found")

    latest_bar = store.bars[symbol][-1]

    return {
        "symbol": symbol,
        "trade": {
            "t": datetime.now(UTC).isoformat(),
            "x": "V",
            "p": latest_bar["c"],
            "s": 100,
            "c": ["@"],
            "i": 12345,
            "z": "A",
        },
    }


# ==========================================
# Trading endpoints
# ==========================================


@app.get("/v2/account")
async def get_account():
    """Get account information."""
    return store.account


@app.get("/v2/positions")
async def list_positions():
    """List all positions."""
    return list(store.positions.values())


@app.get("/v2/positions/{symbol}")
async def get_position(symbol: str):
    """Get position for a symbol."""
    symbol = symbol.upper()

    if symbol not in store.positions:
        raise HTTPException(status_code=404, detail="Position not found")

    return store.positions[symbol]


@app.post("/v2/orders")
async def create_order(order: OrderRequest):
    """Create a new order."""
    order_id = str(uuid4())
    client_order_id = order.client_order_id or str(uuid4())

    # Get current price for the symbol
    symbol = order.symbol.upper()
    current_price = 100.0  # Default
    if symbol in store.bars and store.bars[symbol]:
        current_price = store.bars[symbol][-1]["c"]

    # Calculate quantity if notional is provided
    qty = order.qty
    if qty is None and order.notional:
        qty = order.notional / current_price

    created_order = {
        "id": order_id,
        "client_order_id": client_order_id,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "submitted_at": datetime.now(UTC).isoformat(),
        "filled_at": datetime.now(UTC).isoformat(),
        "expired_at": None,
        "canceled_at": None,
        "failed_at": None,
        "asset_id": str(uuid4()),
        "symbol": symbol,
        "asset_class": "us_equity",
        "qty": str(qty),
        "filled_qty": str(qty),  # Instantly filled for mock
        "type": order.type,
        "side": order.side,
        "time_in_force": order.time_in_force,
        "limit_price": str(order.limit_price) if order.limit_price else None,
        "stop_price": str(order.stop_price) if order.stop_price else None,
        "filled_avg_price": str(current_price),
        "status": "filled",  # Instantly filled for mock
        "extended_hours": False,
        "legs": None,
    }

    store.orders[order_id] = created_order

    # Update positions
    position_change = float(qty) if order.side == "buy" else -float(qty)
    if symbol in store.positions:
        current_qty = float(store.positions[symbol]["qty"])
        new_qty = current_qty + position_change
        if new_qty == 0:
            del store.positions[symbol]
        else:
            store.positions[symbol]["qty"] = str(new_qty)
            store.positions[symbol]["market_value"] = str(new_qty * current_price)
    elif position_change > 0:
        store.positions[symbol] = {
            "asset_id": str(uuid4()),
            "symbol": symbol,
            "exchange": "NASDAQ",
            "asset_class": "us_equity",
            "qty": str(position_change),
            "avg_entry_price": str(current_price),
            "side": "long",
            "market_value": str(position_change * current_price),
            "cost_basis": str(position_change * current_price),
            "unrealized_pl": "0",
            "unrealized_plpc": "0",
            "current_price": str(current_price),
        }

    return created_order


@app.get("/v2/orders")
async def list_orders(
    status: str = Query("all"),
    limit: int = Query(50),
    direction: str = Query("desc"),
):
    """List orders."""
    orders = list(store.orders.values())

    if status != "all":
        orders = [o for o in orders if o["status"] == status]

    return orders[-limit:]


@app.get("/v2/orders/{order_id}")
async def get_order(order_id: str):
    """Get order by ID."""
    if order_id not in store.orders:
        raise HTTPException(status_code=404, detail="Order not found")
    return store.orders[order_id]


@app.delete("/v2/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order."""
    if order_id not in store.orders:
        raise HTTPException(status_code=404, detail="Order not found")

    order = store.orders[order_id]
    if order["status"] == "filled":
        raise HTTPException(status_code=422, detail="Cannot cancel filled order")

    order["status"] = "canceled"
    order["canceled_at"] = datetime.now(UTC).isoformat()
    return {"message": "Order canceled"}


# ==========================================
# Test helper endpoints
# ==========================================


@app.post("/_test/set_bars")
async def set_bars(request: SetBarsRequest):
    """Set bar data for a symbol (test helper)."""
    store.bars[request.symbol.upper()] = request.bars
    return {"message": f"Set {len(request.bars)} bars for {request.symbol}"}


@app.post("/_test/reset")
async def reset_store():
    """Reset all mock data (test helper)."""
    global store
    store = MockDataStore()
    return {"message": "Store reset"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "alpaca-mock"}


# ==========================================
# Server management utilities
# ==========================================


@dataclass
class MockServer:
    """Mock server handle for tests."""

    process: subprocess.Popen
    port: int
    base_url: str

    def stop(self):
        """Stop the mock server."""
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


@contextmanager
def create_alpaca_mock_server(port: int = 8888):
    """Start the Alpaca mock server as a subprocess.

    Usage:
        with create_alpaca_mock_server() as server:
            response = httpx.get(f"{server.base_url}/v2/account")

    Yields:
        MockServer with process handle and connection info
    """
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.mocks.alpaca_mock:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://localhost:{port}"
    server = MockServer(process=process, port=port, base_url=base_url)

    try:
        # Wait for server to be ready
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                response = httpx.get(f"{base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    break
            except httpx.RequestError, httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise TimeoutError("Alpaca mock server did not start within 10s")

        yield server
    finally:
        server.stop()
