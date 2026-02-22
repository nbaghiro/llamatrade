# Alpaca API Technical Guide

A comprehensive guide to using the Alpaca Trading API for algorithmic trading, with practical examples mapping to common trading strategies and asset classes.

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Authentication](#authentication)
3. [Account Management](#account-management)
4. [Assets API](#assets-api)
5. [Order Management](#order-management)
6. [Position Management](#position-management)
7. [Market Data API](#market-data-api)
8. [Real-Time Streaming](#real-time-streaming)
9. [Practical Strategy Examples](#practical-strategy-examples)
10. [Error Handling & Best Practices](#error-handling--best-practices)

---

## Overview & Architecture

### What is Alpaca?

Alpaca is a commission-free trading API that allows you to programmatically trade US equities, options, and cryptocurrencies. It provides both a **paper trading** environment (simulated) and **live trading** with real money.

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        YOUR TRADING SYSTEM                          │
├─────────────────────────────────────────────────────────────────────┤
│  Strategy Logic → Signal Generation → Risk Check → Order Decision   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ALPACA API LAYER                            │
├──────────────────┬──────────────────┬───────────────────────────────┤
│   Trading API    │   Market Data    │      Streaming (WebSocket)    │
│                  │                  │                               │
│  • Orders        │  • Historical    │  • Real-time quotes           │
│  • Positions     │    bars/quotes   │  • Real-time trades           │
│  • Account       │  • Snapshots     │  • Order updates              │
│  • Assets        │  • News          │  • Account updates            │
└──────────────────┴──────────────────┴───────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          EXCHANGES                                  │
│         NYSE, NASDAQ, IEX, CBOE, Crypto Exchanges                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Base URLs

| Environment | Trading API | Market Data | Streaming |
|-------------|-------------|-------------|-----------|
| **Paper** | `https://paper-api.alpaca.markets` | `https://data.alpaca.markets` | `wss://stream.data.alpaca.markets` |
| **Live** | `https://api.alpaca.markets` | `https://data.alpaca.markets` | `wss://stream.data.alpaca.markets` |

### Supported Asset Classes

| Asset Class | API Value | Trading Hours | Features |
|-------------|-----------|---------------|----------|
| **US Equities** | `us_equity` | 9:30 AM - 4:00 PM ET | Fractional shares, short selling |
| **US Options** | `us_option` | 9:30 AM - 4:00 PM ET | Up to Level 3 |
| **Crypto** | `crypto` | 24/7 | Spot trading |

---

## Authentication

### API Keys

Alpaca uses API key-based authentication. You need two credentials:

```
APCA-API-KEY-ID:     Your public API key identifier
APCA-API-SECRET-KEY: Your private secret key (keep this secure!)
```

### HTTP Header Authentication

Every REST API request must include these headers:

```http
GET /v2/account HTTP/1.1
Host: paper-api.alpaca.markets
APCA-API-KEY-ID: PKXXXXXXXXXXXXXXXX
APCA-API-SECRET-KEY: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Python Example

```python
import requests

API_KEY = "PKXXXXXXXXXXXXXXXX"
API_SECRET = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
BASE_URL = "https://paper-api.alpaca.markets"

headers = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET
}

# Test authentication by fetching account
response = requests.get(f"{BASE_URL}/v2/account", headers=headers)
account = response.json()
print(f"Account Status: {account['status']}")
print(f"Buying Power: ${account['buying_power']}")
```

### WebSocket Authentication

For streaming connections, authenticate via message after connecting:

```json
{
  "action": "auth",
  "key": "PKXXXXXXXXXXXXXXXX",
  "secret": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
}
```

Success response:
```json
[{"T": "success", "msg": "authenticated"}]
```

**Important**: You have 10 seconds to authenticate after connecting or the connection will be closed.

---

## Account Management

### Get Account Details

The account endpoint provides your current financial state, margin info, and trading permissions.

**Endpoint**: `GET /v2/account`

**Response Fields Explained**:

```python
response = requests.get(f"{BASE_URL}/v2/account", headers=headers)
account = response.json()
```

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `cash` | string | Settled cash balance | "50000.00" |
| `buying_power` | string | Total available for trading | "200000.00" |
| `equity` | string | Cash + market value of positions | "75000.00" |
| `portfolio_value` | string | Total portfolio worth | "75000.00" |
| `long_market_value` | string | Value of long positions | "25000.00" |
| `short_market_value` | string | Value of short positions | "-5000.00" |
| `pattern_day_trader` | bool | PDT flag (>4 day trades in 5 days) | false |
| `daytrade_count` | int | Day trades in last 5 days | 2 |
| `multiplier` | string | Margin multiplier (1, 2, or 4) | "4" |
| `shorting_enabled` | bool | Can short sell | true |

### Understanding Buying Power

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUYING POWER TYPES                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  buying_power           Total available (includes margin)       │
│       │                                                         │
│       ├── daytrading_buying_power   For intraday (4x equity)    │
│       │                                                         │
│       └── regt_buying_power         For overnight (2x equity)   │
│                                                                 │
│  options_buying_power   Separate allocation for options         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Example Calculation**:
```
Account Equity:              $50,000
Day Trading Buying Power:    $200,000  (4x for intraday)
RegT Buying Power:           $100,000  (2x for overnight)
```

### Checking If You Can Trade

```python
def can_trade(account):
    """Check if account is ready for trading"""
    checks = {
        "account_active": account["status"] == "ACTIVE",
        "not_blocked": not account["trading_blocked"],
        "has_buying_power": float(account["buying_power"]) > 0,
        "not_pdt_restricted": not (
            account["pattern_day_trader"] and
            float(account["equity"]) < 25000
        )
    }
    return all(checks.values()), checks
```

---

## Assets API

The Assets API tells you what you can trade and the characteristics of each asset.

### Get All Tradeable Assets

**Endpoint**: `GET /v2/assets`

**Query Parameters**:
| Parameter | Description | Example |
|-----------|-------------|---------|
| `status` | Filter by status | `active` |
| `asset_class` | Filter by class | `us_equity`, `crypto` |
| `exchange` | Filter by exchange | `NYSE`, `NASDAQ` |

```python
# Get all active US equities
params = {"status": "active", "asset_class": "us_equity"}
response = requests.get(f"{BASE_URL}/v2/assets", headers=headers, params=params)
assets = response.json()

# Find specific asset
aapl = next(a for a in assets if a["symbol"] == "AAPL")
```

### Asset Object Fields

```python
{
    "id": "904837e3-3b76-47ec-b432-046db621571b",
    "class": "us_equity",
    "exchange": "NASDAQ",
    "symbol": "AAPL",
    "name": "Apple Inc. Common Stock",
    "status": "active",
    "tradable": true,
    "marginable": true,
    "shortable": true,
    "easy_to_borrow": true,
    "fractionable": true,
    "min_order_size": "1",
    "min_trade_increment": "0.0001",
    "price_increment": "0.01"
}
```

**Key Fields for Trading Logic**:

| Field | Why It Matters |
|-------|---------------|
| `tradable` | Can you trade it right now? |
| `shortable` | Can you short sell? |
| `easy_to_borrow` | Low borrow cost for shorting |
| `fractionable` | Can buy fractional shares (e.g., 0.5 shares) |
| `marginable` | Can use margin to buy |

### Get Single Asset

```python
# By symbol
response = requests.get(f"{BASE_URL}/v2/assets/AAPL", headers=headers)
aapl = response.json()

# Check if we can trade it
if aapl["tradable"] and aapl["status"] == "active":
    print(f"{aapl['symbol']} is ready to trade")
```

---

## Order Management

Orders are the core of execution. Alpaca supports various order types that map directly to our trading primitives.

### Order Types Mapping

| Our Concept | Alpaca `type` | Description |
|-------------|---------------|-------------|
| Market Order | `market` | Execute immediately at best price |
| Limit Order | `limit` | Execute at specified price or better |
| Stop Order | `stop` | Trigger market order at price |
| Stop-Limit | `stop_limit` | Trigger limit order at price |
| Trailing Stop | `trailing_stop` | Dynamic stop that follows price |

### Time-in-Force Options

| TIF | Alpaca Value | Behavior |
|-----|--------------|----------|
| Day | `day` | Cancel at market close if unfilled |
| GTC | `gtc` | Good until canceled (max 90 days) |
| IOC | `ioc` | Fill immediately or cancel |
| FOK | `fok` | Fill entirely or cancel |
| Market Open | `opg` | Execute at open auction |
| Market Close | `cls` | Execute at close auction |

### Creating Orders

**Endpoint**: `POST /v2/orders`

#### Market Order Example

*Scenario: Your momentum strategy signals BUY on AAPL*

```python
def place_market_order(symbol, qty, side):
    """
    Place a market order for immediate execution.

    Use when: You want to enter/exit NOW regardless of exact price.
    Best for: Liquid stocks, urgent exits, stop-loss triggered trades.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,           # "buy" or "sell"
        "type": "market",
        "time_in_force": "day"
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Execute: Buy 100 shares of AAPL at market
order = place_market_order("AAPL", 100, "buy")
print(f"Order ID: {order['id']}, Status: {order['status']}")
```

#### Limit Order Example

*Scenario: Mean reversion strategy wants to buy MSFT if it drops to $400*

```python
def place_limit_order(symbol, qty, side, limit_price):
    """
    Place a limit order at a specific price.

    Use when: You have a target entry/exit price.
    Best for: Mean reversion entries, scaling into positions.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "limit_price": str(limit_price),
        "time_in_force": "gtc"  # Keep open until filled
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Place limit buy: 50 shares of MSFT at $400
order = place_limit_order("MSFT", 50, "buy", 400.00)
```

#### Stop-Loss Order Example

*Scenario: You own TSLA at $250, want to limit loss to 5%*

```python
def place_stop_order(symbol, qty, stop_price):
    """
    Place a stop order for risk management.

    Use when: You want to exit if price moves against you.
    Best for: Stop losses, breakout entries.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "stop",
        "stop_price": str(stop_price),
        "time_in_force": "gtc"
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Stop loss: Sell 25 TSLA if price drops to $237.50 (5% below $250)
entry_price = 250.00
stop_percent = 0.05
stop_price = entry_price * (1 - stop_percent)
order = place_stop_order("TSLA", 25, stop_price)
```

#### Trailing Stop Order Example

*Scenario: Lock in profits as NVDA rises*

```python
def place_trailing_stop(symbol, qty, trail_percent):
    """
    Place a trailing stop that follows price up.

    Use when: You want to let winners run while protecting gains.
    Best for: Trend following, momentum strategies.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "trailing_stop",
        "trail_percent": str(trail_percent),
        "time_in_force": "gtc"
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Trailing stop: Sell NVDA if price drops 3% from high
order = place_trailing_stop("NVDA", 10, 3.0)
```

### Bracket Orders (Entry + Stop Loss + Take Profit)

*Scenario: Complete trade setup for a breakout strategy*

A bracket order is a complete trade: entry order with automatic stop-loss and take-profit orders attached.

```python
def place_bracket_order(symbol, qty, side, limit_price, stop_loss, take_profit):
    """
    Place a bracket order with built-in risk management.

    Use when: You want automatic exits at target or stop.
    Best for: Any strategy where you know your R:R upfront.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "limit_price": str(limit_price),
        "time_in_force": "gtc",
        "order_class": "bracket",
        "take_profit": {
            "limit_price": str(take_profit)
        },
        "stop_loss": {
            "stop_price": str(stop_loss)
        }
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Breakout trade on AMD:
# Entry: Buy at $150 (breakout level)
# Stop: $145 (below support)
# Target: $165 (3:1 reward/risk)
order = place_bracket_order(
    symbol="AMD",
    qty=50,
    side="buy",
    limit_price=150.00,
    stop_loss=145.00,
    take_profit=165.00
)
```

### OCO Orders (One-Cancels-Other)

*Scenario: Exit position at either profit target OR stop loss*

```python
def place_oco_order(symbol, qty, take_profit_price, stop_loss_price):
    """
    Place OCO for existing position exit.

    Use when: You have a position and want automatic exit at either level.
    """
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "limit",
        "limit_price": str(take_profit_price),
        "time_in_force": "gtc",
        "order_class": "oco",
        "stop_loss": {
            "stop_price": str(stop_loss_price)
        }
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()
```

### Fractional Shares (Notional Orders)

*Scenario: Invest exactly $500 in GOOGL regardless of share price*

```python
def place_notional_order(symbol, dollar_amount, side):
    """
    Place order by dollar amount instead of share quantity.

    Use when: You want to invest a specific dollar amount.
    Best for: Portfolio allocation, dollar-cost averaging.
    """
    order = {
        "symbol": symbol,
        "notional": str(dollar_amount),  # Use notional instead of qty
        "side": side,
        "type": "market",
        "time_in_force": "day"
    }

    response = requests.post(
        f"{BASE_URL}/v2/orders",
        headers=headers,
        json=order
    )
    return response.json()

# Invest exactly $500 in GOOGL
order = place_notional_order("GOOGL", 500.00, "buy")
# Result: You'll own ~2.78 shares if GOOGL is at $180
```

### Order Status Lifecycle

```
┌─────────┐     ┌─────────┐     ┌────────────────┐     ┌────────┐
│   new   │ ──► │ accepted│ ──► │partially_filled│ ──► │ filled │
└─────────┘     └─────────┘     └────────────────┘     └────────┘
     │               │                   │
     │               ▼                   │
     │          ┌─────────┐              │
     └────────► │ rejected│ ◄────────────┘
                └─────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌─────────┐    ┌──────────┐    ┌─────────┐
│canceled │    │ expired  │    │ replaced│
└─────────┘    └──────────┘    └─────────┘
```

### Get Orders

```python
# Get all open orders
response = requests.get(
    f"{BASE_URL}/v2/orders",
    headers=headers,
    params={"status": "open"}
)
open_orders = response.json()

# Get specific order
order_id = "904837e3-3b76-47ec-b432-046db621571b"
response = requests.get(f"{BASE_URL}/v2/orders/{order_id}", headers=headers)
order = response.json()
```

### Cancel Orders

```python
# Cancel specific order
order_id = "904837e3-3b76-47ec-b432-046db621571b"
response = requests.delete(f"{BASE_URL}/v2/orders/{order_id}", headers=headers)

# Cancel ALL open orders
response = requests.delete(f"{BASE_URL}/v2/orders", headers=headers)
```

### Replace/Modify Orders

```python
def replace_order(order_id, new_qty=None, new_limit_price=None):
    """Modify an existing order (creates replacement)"""
    payload = {}
    if new_qty:
        payload["qty"] = str(new_qty)
    if new_limit_price:
        payload["limit_price"] = str(new_limit_price)

    response = requests.patch(
        f"{BASE_URL}/v2/orders/{order_id}",
        headers=headers,
        json=payload
    )
    return response.json()
```

---

## Position Management

Positions represent your current holdings. The API provides real-time P&L and market values.

### Get All Positions

**Endpoint**: `GET /v2/positions`

```python
response = requests.get(f"{BASE_URL}/v2/positions", headers=headers)
positions = response.json()

for pos in positions:
    print(f"""
    Symbol: {pos['symbol']}
    Qty: {pos['qty']} shares
    Market Value: ${pos['market_value']}
    Unrealized P&L: ${pos['unrealized_pl']} ({pos['unrealized_plpc']}%)
    """)
```

### Position Object Fields

```python
{
    "asset_id": "904837e3-3b76-47ec-b432-046db621571b",
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "asset_class": "us_equity",
    "qty": "100",                      # Shares owned (negative = short)
    "side": "long",                    # "long" or "short"
    "market_value": "17850.00",        # Current value
    "cost_basis": "15000.00",          # What you paid
    "avg_entry_price": "150.00",       # Average purchase price
    "unrealized_pl": "2850.00",        # Unrealized profit/loss
    "unrealized_plpc": "0.19",         # P&L as percentage (19%)
    "unrealized_intraday_pl": "150.00",# Today's P&L
    "unrealized_intraday_plpc": "0.008",# Today's P&L %
    "current_price": "178.50",         # Current market price
    "lastday_price": "177.00",         # Yesterday's close
    "change_today": "0.0085"           # Today's price change %
}
```

### Get Single Position

```python
symbol = "AAPL"
response = requests.get(f"{BASE_URL}/v2/positions/{symbol}", headers=headers)
position = response.json()
```

### Close Position

```python
def close_position(symbol, qty=None, percentage=None):
    """
    Close all or part of a position.

    qty: Specific number of shares to close
    percentage: Percentage of position to close (0-100)
    """
    params = {}
    if qty:
        params["qty"] = str(qty)
    elif percentage:
        params["percentage"] = str(percentage)

    response = requests.delete(
        f"{BASE_URL}/v2/positions/{symbol}",
        headers=headers,
        params=params
    )
    return response.json()

# Close entire position
close_position("AAPL")

# Close half the position
close_position("AAPL", percentage=50)

# Close specific quantity
close_position("AAPL", qty=25)
```

### Close All Positions

```python
# Emergency: Close everything
response = requests.delete(
    f"{BASE_URL}/v2/positions",
    headers=headers,
    params={"cancel_orders": "true"}  # Also cancel open orders
)
```

### Portfolio Analysis Helper

```python
def analyze_portfolio():
    """Get portfolio summary with risk metrics"""
    response = requests.get(f"{BASE_URL}/v2/positions", headers=headers)
    positions = response.json()

    total_value = 0
    total_pl = 0
    by_sector = {}

    for pos in positions:
        value = float(pos["market_value"])
        pl = float(pos["unrealized_pl"])
        total_value += value
        total_pl += pl

    return {
        "total_market_value": total_value,
        "total_unrealized_pl": total_pl,
        "position_count": len(positions),
        "positions": positions
    }
```

---

## Market Data API

Market data is essential for strategy signals. Alpaca provides both historical and real-time data.

### Historical Bars (OHLCV)

**Endpoint**: `GET /v2/stocks/{symbol}/bars` (single) or `GET /v2/stocks/bars` (multi)

#### Timeframe Options

| Timeframe | Format | Use Case |
|-----------|--------|----------|
| 1 Minute | `1Min` | Intraday scalping |
| 5 Minutes | `5Min` | Intraday swing |
| 15 Minutes | `15Min` | Intraday |
| 1 Hour | `1Hour` | Swing trading |
| 1 Day | `1Day` | Position trading |
| 1 Week | `1Week` | Long-term |
| 1 Month | `1Month` | Long-term |

#### Example: Get Daily Bars for Moving Average

*Scenario: Calculate 20-day and 50-day moving averages for trend following*

```python
import pandas as pd
from datetime import datetime, timedelta

DATA_URL = "https://data.alpaca.markets"

def get_bars(symbol, timeframe, start, end, limit=1000):
    """Fetch historical OHLCV bars"""
    response = requests.get(
        f"{DATA_URL}/v2/stocks/{symbol}/bars",
        headers=headers,
        params={
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": limit,
            "adjustment": "split"  # Adjust for splits
        }
    )
    return response.json()

# Get 60 days of daily bars for AAPL
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

data = get_bars("AAPL", "1Day", start_date, end_date)
bars = data["bars"]

# Convert to DataFrame for analysis
df = pd.DataFrame(bars)
df["t"] = pd.to_datetime(df["t"])
df.set_index("t", inplace=True)

# Calculate moving averages (trend following strategy)
df["sma_20"] = df["c"].rolling(window=20).mean()
df["sma_50"] = df["c"].rolling(window=50).mean()

# Generate signal
df["signal"] = (df["sma_20"] > df["sma_50"]).astype(int)
```

#### Bar Response Fields

```python
{
    "t": "2024-01-15T14:30:00Z",  # Timestamp
    "o": 185.50,                   # Open
    "h": 186.20,                   # High
    "l": 185.10,                   # Low
    "c": 185.90,                   # Close
    "v": 1250000,                  # Volume
    "n": 8500,                     # Number of trades
    "vw": 185.65                   # Volume-weighted average price
}
```

### Multi-Symbol Bars

*Scenario: Compare multiple stocks for relative strength momentum*

```python
def get_multi_bars(symbols, timeframe, start, end):
    """Fetch bars for multiple symbols at once"""
    response = requests.get(
        f"{DATA_URL}/v2/stocks/bars",
        headers=headers,
        params={
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start,
            "end": end
        }
    )
    return response.json()

# Get daily bars for tech sector comparison
tech_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
data = get_multi_bars(tech_symbols, "1Day", "2024-01-01", "2024-01-31")

# Calculate 1-month returns for momentum ranking
returns = {}
for symbol in tech_symbols:
    bars = data["bars"][symbol]
    first_close = bars[0]["c"]
    last_close = bars[-1]["c"]
    returns[symbol] = (last_close - first_close) / first_close

# Rank by momentum (highest return = strongest)
ranked = sorted(returns.items(), key=lambda x: x[1], reverse=True)
print("Momentum Ranking:", ranked)
```

### Latest Quote

**Endpoint**: `GET /v2/stocks/{symbol}/quotes/latest`

```python
def get_latest_quote(symbol):
    """Get current bid/ask spread"""
    response = requests.get(
        f"{DATA_URL}/v2/stocks/{symbol}/quotes/latest",
        headers=headers
    )
    return response.json()

quote = get_latest_quote("AAPL")
# {
#     "symbol": "AAPL",
#     "quote": {
#         "ap": 185.50,  # Ask price
#         "as": 300,     # Ask size
#         "bp": 185.48,  # Bid price
#         "bs": 400,     # Bid size
#         "t": "2024-01-15T14:30:00.123Z"
#     }
# }

bid = quote["quote"]["bp"]
ask = quote["quote"]["ap"]
spread = ask - bid
spread_pct = (spread / ask) * 100
print(f"Spread: ${spread:.2f} ({spread_pct:.3f}%)")
```

### Latest Trade

**Endpoint**: `GET /v2/stocks/{symbol}/trades/latest`

```python
def get_latest_trade(symbol):
    """Get most recent executed trade"""
    response = requests.get(
        f"{DATA_URL}/v2/stocks/{symbol}/trades/latest",
        headers=headers
    )
    return response.json()

trade = get_latest_trade("AAPL")
# {
#     "symbol": "AAPL",
#     "trade": {
#         "p": 185.49,   # Price
#         "s": 100,      # Size
#         "t": "2024-01-15T14:30:00.456Z",
#         "x": "V"       # Exchange code
#     }
# }
```

### Snapshot (All-in-One)

**Endpoint**: `GET /v2/stocks/{symbol}/snapshot`

Get quote, trade, minute bar, daily bar, and previous daily bar in one call.

```python
def get_snapshot(symbol):
    """Get comprehensive current state"""
    response = requests.get(
        f"{DATA_URL}/v2/stocks/{symbol}/snapshot",
        headers=headers
    )
    return response.json()

snapshot = get_snapshot("AAPL")
# Contains: latestQuote, latestTrade, minuteBar, dailyBar, prevDailyBar
```

### Crypto Data

```python
CRYPTO_URL = "https://data.alpaca.markets"

def get_crypto_bars(symbol, timeframe, start, end):
    """Fetch crypto OHLCV data"""
    response = requests.get(
        f"{CRYPTO_URL}/v1beta3/crypto/us/bars",
        headers=headers,
        params={
            "symbols": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end
        }
    )
    return response.json()

# Get hourly BTC bars
btc_data = get_crypto_bars("BTC/USD", "1Hour", "2024-01-01", "2024-01-02")
```

---

## Real-Time Streaming

WebSocket streaming provides real-time market data and order updates with minimal latency.

### Connection Setup

```python
import websocket
import json

STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"  # IEX feed (free)
# STREAM_URL = "wss://stream.data.alpaca.markets/v2/sip"  # Full SIP (paid)

class AlpacaStream:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws = None

    def on_open(self, ws):
        """Authenticate on connection"""
        auth_message = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.api_secret
        }
        ws.send(json.dumps(auth_message))

    def on_message(self, ws, message):
        """Handle incoming messages"""
        data = json.loads(message)
        for item in data:
            msg_type = item.get("T")

            if msg_type == "success":
                print(f"Auth: {item['msg']}")
                self.subscribe()
            elif msg_type == "t":  # Trade
                self.on_trade(item)
            elif msg_type == "q":  # Quote
                self.on_quote(item)
            elif msg_type == "b":  # Bar
                self.on_bar(item)

    def subscribe(self):
        """Subscribe to symbols"""
        sub_message = {
            "action": "subscribe",
            "trades": ["AAPL", "MSFT"],
            "quotes": ["AAPL"],
            "bars": ["AAPL"]
        }
        self.ws.send(json.dumps(sub_message))

    def on_trade(self, trade):
        """Process real-time trade"""
        print(f"Trade: {trade['S']} @ ${trade['p']} x {trade['s']}")

    def on_quote(self, quote):
        """Process real-time quote"""
        print(f"Quote: {quote['S']} Bid: ${quote['bp']} Ask: ${quote['ap']}")

    def on_bar(self, bar):
        """Process real-time bar (minute)"""
        print(f"Bar: {bar['S']} O:{bar['o']} H:{bar['h']} L:{bar['l']} C:{bar['c']}")

    def connect(self):
        """Start streaming connection"""
        self.ws = websocket.WebSocketApp(
            STREAM_URL,
            on_open=self.on_open,
            on_message=self.on_message
        )
        self.ws.run_forever()
```

### Message Types

| Type | Field `T` | Description |
|------|-----------|-------------|
| Trade | `t` | Executed trade |
| Quote | `q` | Bid/ask update |
| Bar | `b` | Minute bar |
| Status | `s` | Trading status |
| LULD | `l` | Limit up/down bands |

### Trade Message Format

```python
{
    "T": "t",           # Type: trade
    "S": "AAPL",        # Symbol
    "p": 185.50,        # Price
    "s": 100,           # Size
    "t": "2024-01-15T14:30:00.123456789Z",  # Timestamp (nanoseconds)
    "x": "V",           # Exchange
    "c": ["@", "I"]     # Conditions
}
```

### Quote Message Format

```python
{
    "T": "q",           # Type: quote
    "S": "AAPL",        # Symbol
    "bp": 185.48,       # Bid price
    "bs": 400,          # Bid size
    "ap": 185.50,       # Ask price
    "as": 300,          # Ask size
    "t": "2024-01-15T14:30:00.123456789Z",
    "x": "V",           # Exchange
    "c": "R"            # Condition
}
```

### Subscribing to Updates

```python
# Subscribe to specific symbols
{
    "action": "subscribe",
    "trades": ["AAPL", "MSFT", "GOOGL"],
    "quotes": ["AAPL"],
    "bars": ["SPY"]
}

# Subscribe to ALL symbols (wildcard)
{
    "action": "subscribe",
    "trades": ["*"]  # All trades (requires paid plan)
}

# Unsubscribe
{
    "action": "unsubscribe",
    "trades": ["MSFT"]
}
```

---

## Practical Strategy Examples

### Example 1: Simple Moving Average Crossover

*Complete implementation of a trend following strategy*

```python
import time
from datetime import datetime, timedelta

class SMACrossoverStrategy:
    """
    Strategy: Buy when 10-day SMA crosses above 30-day SMA
              Sell when 10-day SMA crosses below 30-day SMA
    """

    def __init__(self, symbol, fast_period=10, slow_period=30):
        self.symbol = symbol
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.position = None

    def get_historical_data(self):
        """Fetch enough history for indicators"""
        end = datetime.now()
        start = end - timedelta(days=self.slow_period + 10)

        response = requests.get(
            f"{DATA_URL}/v2/stocks/{self.symbol}/bars",
            headers=headers,
            params={
                "timeframe": "1Day",
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d")
            }
        )
        return response.json()["bars"]

    def calculate_signals(self, bars):
        """Calculate SMAs and generate signal"""
        closes = [bar["c"] for bar in bars]

        fast_sma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_sma = sum(closes[-self.slow_period:]) / self.slow_period

        prev_closes = closes[:-1]
        prev_fast_sma = sum(prev_closes[-self.fast_period:]) / self.fast_period
        prev_slow_sma = sum(prev_closes[-self.slow_period:]) / self.slow_period

        # Crossover detection
        bullish_cross = prev_fast_sma <= prev_slow_sma and fast_sma > slow_sma
        bearish_cross = prev_fast_sma >= prev_slow_sma and fast_sma < slow_sma

        return {
            "fast_sma": fast_sma,
            "slow_sma": slow_sma,
            "signal": "BUY" if bullish_cross else "SELL" if bearish_cross else "HOLD"
        }

    def get_current_position(self):
        """Check if we have a position"""
        try:
            response = requests.get(
                f"{BASE_URL}/v2/positions/{self.symbol}",
                headers=headers
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None

    def execute(self):
        """Run one iteration of the strategy"""
        bars = self.get_historical_data()
        analysis = self.calculate_signals(bars)
        position = self.get_current_position()

        print(f"Fast SMA: {analysis['fast_sma']:.2f}")
        print(f"Slow SMA: {analysis['slow_sma']:.2f}")
        print(f"Signal: {analysis['signal']}")

        if analysis["signal"] == "BUY" and not position:
            # Calculate position size (2% of portfolio)
            account = requests.get(f"{BASE_URL}/v2/account", headers=headers).json()
            buying_power = float(account["buying_power"])
            position_value = buying_power * 0.02

            # Get current price
            quote = get_latest_quote(self.symbol)
            price = quote["quote"]["ap"]
            qty = int(position_value / price)

            if qty > 0:
                order = place_market_order(self.symbol, qty, "buy")
                print(f"BUY ORDER: {order}")

        elif analysis["signal"] == "SELL" and position:
            close_position(self.symbol)
            print(f"CLOSED POSITION")

# Run strategy
strategy = SMACrossoverStrategy("AAPL")
strategy.execute()
```

### Example 2: RSI Mean Reversion

*Buy oversold, sell overbought*

```python
class RSIMeanReversionStrategy:
    """
    Strategy: Buy when RSI < 30 (oversold)
              Sell when RSI > 70 (overbought)
    """

    def __init__(self, symbol, period=14, oversold=30, overbought=70):
        self.symbol = symbol
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def calculate_rsi(self, bars):
        """Calculate RSI indicator"""
        closes = [bar["c"] for bar in bars]

        gains = []
        losses = []

        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))

        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def execute(self):
        """Run strategy"""
        # Get 30 days of data
        end = datetime.now()
        start = end - timedelta(days=30)

        response = requests.get(
            f"{DATA_URL}/v2/stocks/{self.symbol}/bars",
            headers=headers,
            params={
                "timeframe": "1Day",
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d")
            }
        )
        bars = response.json()["bars"]

        rsi = self.calculate_rsi(bars)
        position = self.get_current_position()

        print(f"RSI: {rsi:.2f}")

        if rsi < self.oversold and not position:
            print("RSI oversold - BUY signal")
            # Place buy order...

        elif rsi > self.overbought and position:
            print("RSI overbought - SELL signal")
            # Close position...
```

### Example 3: Pairs Trading (Statistical Arbitrage)

*Trade the spread between two correlated stocks*

```python
class PairsTradingStrategy:
    """
    Strategy: Trade mean reversion of spread between two correlated stocks
    """

    def __init__(self, symbol_a, symbol_b, lookback=20, entry_z=2.0, exit_z=0.5):
        self.symbol_a = symbol_a  # e.g., "KO" (Coca-Cola)
        self.symbol_b = symbol_b  # e.g., "PEP" (Pepsi)
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z

    def get_pair_data(self):
        """Fetch data for both symbols"""
        end = datetime.now()
        start = end - timedelta(days=self.lookback + 10)

        response = requests.get(
            f"{DATA_URL}/v2/stocks/bars",
            headers=headers,
            params={
                "symbols": f"{self.symbol_a},{self.symbol_b}",
                "timeframe": "1Day",
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d")
            }
        )
        return response.json()["bars"]

    def calculate_spread(self, bars):
        """Calculate spread and z-score"""
        prices_a = [bar["c"] for bar in bars[self.symbol_a]]
        prices_b = [bar["c"] for bar in bars[self.symbol_b]]

        # Simple spread (can use hedge ratio from regression)
        spread = [a - b for a, b in zip(prices_a, prices_b)]

        # Z-score
        mean = sum(spread[-self.lookback:]) / self.lookback
        variance = sum((s - mean)**2 for s in spread[-self.lookback:]) / self.lookback
        std = variance ** 0.5

        current_spread = spread[-1]
        z_score = (current_spread - mean) / std if std > 0 else 0

        return {
            "spread": current_spread,
            "mean": mean,
            "z_score": z_score
        }

    def execute(self):
        """Run pairs trading logic"""
        bars = self.get_pair_data()
        analysis = self.calculate_spread(bars)

        print(f"Spread: {analysis['spread']:.2f}")
        print(f"Z-Score: {analysis['z_score']:.2f}")

        if analysis["z_score"] > self.entry_z:
            # Spread too high: Short A, Long B
            print(f"SIGNAL: Short {self.symbol_a}, Long {self.symbol_b}")

        elif analysis["z_score"] < -self.entry_z:
            # Spread too low: Long A, Short B
            print(f"SIGNAL: Long {self.symbol_a}, Short {self.symbol_b}")

        elif abs(analysis["z_score"]) < self.exit_z:
            # Spread reverted: Close positions
            print("SIGNAL: Close all pair positions")

# Run pairs strategy
pairs = PairsTradingStrategy("KO", "PEP")
pairs.execute()
```

---

## Error Handling & Best Practices

### API Error Codes

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request | Check parameters |
| 401 | Unauthorized | Check API keys |
| 403 | Forbidden | Check permissions |
| 404 | Not found | Check symbol/order ID |
| 422 | Unprocessable | Invalid order (e.g., market closed) |
| 429 | Rate limited | Back off and retry |
| 500+ | Server error | Retry with backoff |

### Rate Limits

| Plan | Requests/Minute |
|------|-----------------|
| Free | 200 |
| Algo Trader Plus | 10,000 |

### Robust API Wrapper

```python
import time
from functools import wraps

def retry_with_backoff(max_retries=3, backoff_factor=2):
    """Decorator for automatic retry with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    response = func(*args, **kwargs)

                    if response.status_code == 429:
                        # Rate limited
                        wait_time = backoff_factor ** retries
                        print(f"Rate limited. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        retries += 1
                        continue

                    if response.status_code >= 500:
                        # Server error
                        wait_time = backoff_factor ** retries
                        print(f"Server error. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        retries += 1
                        continue

                    return response

                except Exception as e:
                    print(f"Request failed: {e}")
                    retries += 1
                    if retries < max_retries:
                        time.sleep(backoff_factor ** retries)

            raise Exception(f"Max retries ({max_retries}) exceeded")
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3)
def safe_api_call(method, url, **kwargs):
    """Make API call with automatic retry"""
    return requests.request(method, url, headers=headers, **kwargs)
```

### Order Validation

```python
def validate_order(symbol, qty, side, order_type, **kwargs):
    """Validate order before submission"""
    errors = []

    # Check symbol is tradeable
    asset_response = requests.get(f"{BASE_URL}/v2/assets/{symbol}", headers=headers)
    if asset_response.status_code != 200:
        errors.append(f"Symbol {symbol} not found")
    else:
        asset = asset_response.json()
        if not asset["tradable"]:
            errors.append(f"Symbol {symbol} is not tradeable")
        if side == "sell" and not asset["shortable"]:
            # Check if we have position
            pos_response = requests.get(f"{BASE_URL}/v2/positions/{symbol}", headers=headers)
            if pos_response.status_code != 200:
                errors.append(f"Cannot short {symbol} - not shortable and no position")

    # Check buying power
    if side == "buy":
        account = requests.get(f"{BASE_URL}/v2/account", headers=headers).json()
        buying_power = float(account["buying_power"])

        if order_type == "limit":
            estimated_cost = qty * kwargs.get("limit_price", 0)
        else:
            quote = get_latest_quote(symbol)
            estimated_cost = qty * quote["quote"]["ap"]

        if estimated_cost > buying_power:
            errors.append(f"Insufficient buying power: need ${estimated_cost:.2f}, have ${buying_power:.2f}")

    # Check market hours for day orders
    if kwargs.get("time_in_force") == "day":
        clock = requests.get(f"{BASE_URL}/v2/clock", headers=headers).json()
        if not clock["is_open"]:
            errors.append("Market is closed - 'day' orders will be queued")

    return errors

# Use before placing order
errors = validate_order("AAPL", 100, "buy", "market")
if errors:
    print("Validation failed:", errors)
else:
    place_market_order("AAPL", 100, "buy")
```

### Logging Best Practices

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def logged_order(symbol, qty, side, order_type, **kwargs):
    """Place order with comprehensive logging"""
    logger.info(f"Placing {order_type} {side} order: {qty} {symbol}")

    try:
        response = requests.post(
            f"{BASE_URL}/v2/orders",
            headers=headers,
            json={
                "symbol": symbol,
                "qty": str(qty),
                "side": side,
                "type": order_type,
                **kwargs
            }
        )

        if response.status_code == 200:
            order = response.json()
            logger.info(f"Order placed: ID={order['id']}, Status={order['status']}")
            return order
        else:
            logger.error(f"Order failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.exception(f"Order exception: {e}")
        return None
```

---

## Quick Reference

### Essential Endpoints

| Action | Method | Endpoint |
|--------|--------|----------|
| Get Account | GET | `/v2/account` |
| List Assets | GET | `/v2/assets` |
| Place Order | POST | `/v2/orders` |
| Get Orders | GET | `/v2/orders` |
| Cancel Order | DELETE | `/v2/orders/{id}` |
| Get Positions | GET | `/v2/positions` |
| Close Position | DELETE | `/v2/positions/{symbol}` |
| Get Bars | GET | `/v2/stocks/{symbol}/bars` |
| Get Quote | GET | `/v2/stocks/{symbol}/quotes/latest` |

### Order Template

```python
{
    "symbol": "AAPL",
    "qty": "10",                    # OR "notional": "500.00"
    "side": "buy",                  # "buy" or "sell"
    "type": "limit",                # "market", "limit", "stop", "stop_limit", "trailing_stop"
    "time_in_force": "day",         # "day", "gtc", "ioc", "fok", "opg", "cls"
    "limit_price": "150.00",        # Required for limit orders
    "stop_price": "145.00",         # Required for stop orders
    "trail_percent": "2.0",         # For trailing stop
    "extended_hours": true,         # Pre/post market
    "order_class": "bracket",       # "simple", "bracket", "oco", "oto"
    "take_profit": {"limit_price": "160.00"},
    "stop_loss": {"stop_price": "145.00"}
}
```

### WebSocket Subscription

```python
# Connect
wss://stream.data.alpaca.markets/v2/iex

# Authenticate
{"action": "auth", "key": "...", "secret": "..."}

# Subscribe
{"action": "subscribe", "trades": ["AAPL"], "quotes": ["AAPL"], "bars": ["AAPL"]}

# Message types: t=trade, q=quote, b=bar
```

---

*This guide maps directly to the concepts in `algorithmic-trading-strategies.md`. Use them together for a complete algorithmic trading reference.*
