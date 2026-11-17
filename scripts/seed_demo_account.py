"""Seed a polished, internally-consistent demo tenant for LlamaTrade.

Login: ``demo@llamatrade.ai`` / ``demo1234``.

Creates one "lived-in" retail-trader account across every product surface:
auth, billing, strategies (with version history), backtests, the portfolio
double-entry ledger (paper + live accounts / sleeves / events / equity-curve
snapshots), trading (sessions / orders / positions), and the AI copilot
(sessions / messages / memory).

The story is an ordinary trading day, dated relative to the run date: seven
strategies, All-Weather Portfolio live, Recession Radar and Momentum Sectors in
paper, Tech Momentum Rotation stopped and holding cash, Risk Parity backtested
but never run, Dual Momentum edited since its backtest and Pullback Buyer not yet
backtested. Three fills land this morning.

Runs INSIDE the ``portfolio`` container so it can reuse the real ledger kernel
(``src.ledger.*`` + ``src.tasks.equity_snapshot``) rather than hand-writing
balances: every economic event is appended through ``LedgerWriter`` (which
asserts double-entry conservation), sells resolve cost basis through the real
FIFO selector, and the equity curve is produced by the real snapshot computer.

Prices come from one deterministic, correlated price path per symbol, pinned to
anchor prices on the story's key dates. The same path feeds the market-data bars,
the session simulations (fills), the equity snapshots and the backtests, so the
session curves, their marks and the "backtest over the same dates" agree.

Idempotent: it transactionally deletes the demo tenant (found by fixed slug) and
everything scoped to it, then recreates. It never touches another tenant. Global
``plans`` are get-or-created, never deleted.

    docker cp scripts/demo_seed_data llamatrade-portfolio:/app/demo_seed_data
    docker cp scripts/seed_demo_account.py llamatrade-portfolio:/app/seed_demo_account.py
    docker exec -w /app llamatrade-portfolio python seed_demo_account.py

``DEMO_SEED_DRY_RUN=1`` prints the simulated sessions without writing anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

# Make the portfolio service package (`src.*`) importable when invoked as a
# loose script (`python seed_demo_account.py`) rather than a module.
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import numpy as np
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Real ledger kernel: reused, never re-implemented.
from llamatrade_common.utils import encrypt_value
from llamatrade_db import get_session_maker
from llamatrade_db.models import (
    Account,
    AgentMemoryFact,
    AgentMessage,
    AgentSession,
    AlpacaCredentials,
    Backtest,
    BacktestResult,
    Invoice,
    Order,
    PaymentMethod,
    PendingArtifact,
    Plan,
    Position,
    Sleeve,
    SleeveSnapshot,
    Strategy,
    StrategyExecution,
    StrategyVersion,
    Subscription,
    Tenant,
    TradingSession,
    User,
)
from llamatrade_db.models.ledger import LedgerEventType, SleeveStatus, SleeveType
from llamatrade_proto.generated import (
    agent_pb2,
    backtest_pb2,
    billing_pb2,
    common_pb2,
    strategy_pb2,
    trading_pb2,
)

from src.ledger.sizing import Lot as FifoLot
from src.ledger.sizing import select_lots_fifo
from src.ledger.writer import LedgerWriter
from src.tasks.equity_snapshot import SnapshotValue, compute_snapshot_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger("seed_demo")

# Constants

DEMO_EMAIL = "demo@llamatrade.ai"
DEMO_PASSWORD = "demo1234"
DEMO_SLUG = "demo-llamatrade"  # fixed → findable for idempotent re-seed
TENANT_NAME = "Sofia Rivera Trading"

# Deterministic, so every re-seed yields the same tenant/user UUIDs.
DEMO_TENANT_ID = uuid5(NAMESPACE_URL, f"llamatrade:demo:tenant:{DEMO_SLUG}")
DEMO_USER_ID = uuid5(NAMESPACE_URL, f"llamatrade:demo:user:{DEMO_EMAIL}")
FIRST_NAME, LAST_NAME = "Sofia", "Rivera"
DEMO_AVATAR_URL = (
    "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=160&h=160&fit=crop&crop=face"
)

# Pre-generated valid bcrypt hash of "demo1234" (self-verifying via checkpw).
# Fallback for containers without the `bcrypt` module (e.g. portfolio).
_DEMO_PASSWORD_HASH_FALLBACK = "$2b$12$nY6hP1l0Ig4tHIKkdvYX.uHlErnFjher2YvzZaxftVECaQb3DlNXW"

ET = ZoneInfo("America/New_York")
TENANT_CREATED = date(2026, 1, 6)

# Market-data (Timescale) daily bars are seeded so open positions mark to market
# and the equity-vs-SPY overlays have a benchmark series. The store is a separate
# database from the main app DB; the URL falls back to the compose default.
MARKET_DATA_DB_URL = os.getenv(
    "MARKET_DATA_DB_URL",
    "postgresql+asyncpg://postgres:postgres@timescaledb:5432/market_data",
)

# Core mirror of the market-data store's ``bars_daily`` (services/market-data/
# src/store/models.py) — lets the seed write daily bars into the separate
# Timescale DB without importing that service's package. Keep the columns in
# lockstep with the store; the read path serves the newest close as the mark.
_MD_METADATA = MetaData()
_MD_PRICE = Numeric(precision=18, scale=8)
BARS_DAILY = Table(
    "bars_daily",
    _MD_METADATA,
    Column("time", DateTime(timezone=True), nullable=False),
    Column("symbol", String(20), nullable=False),
    Column("open", _MD_PRICE, nullable=False),
    Column("high", _MD_PRICE, nullable=False),
    Column("low", _MD_PRICE, nullable=False),
    Column("close", _MD_PRICE, nullable=False),
    Column("volume", BigInteger, nullable=False),
    Column("vwap", _MD_PRICE, nullable=True),
    Column("trade_count", Integer, nullable=True),
    Column("adjustment", String(10), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=True),
)


# Local checkout: sibling of this script. When copied into the container next to
# the script, the data dir sits at /app/demo_seed_data.
_local_data_dir = Path(__file__).resolve().parent / "demo_seed_data"
DATA_DIR = _local_data_dir if _local_data_dir.exists() else Path("/app/demo_seed_data")

ZERO = Decimal("0")
CENT = Decimal("0.01")
RNG = random.Random(20260713)

# Calendar

NYSE_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(d)
    for d in (
        "2024-01-01 2024-01-15 2024-02-19 2024-03-29 2024-05-27 2024-06-19 2024-07-04 "
        "2024-09-02 2024-11-28 2024-12-25 2025-01-01 2025-01-09 2025-01-20 2025-02-17 "
        "2025-04-18 2025-05-26 2025-06-19 2025-07-04 2025-09-01 2025-11-27 2025-12-25 "
        "2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 "
        "2026-09-07 2026-11-26 2026-12-25 2027-01-01 2027-01-18 2027-02-15 2027-03-26 "
        "2027-05-31 2027-06-18 2027-07-05 2027-09-06 2027-11-25 2027-12-24 2028-01-17 "
        "2028-02-21 2028-04-14 2028-05-29 2028-06-19 2028-07-04 2028-09-04 2028-11-23 "
        "2028-12-25"
    ).split()
)
ONE_DAY = timedelta(days=1)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def trading_on_or_before(d: date) -> date:
    while not is_trading_day(d):
        d -= ONE_DAY
    return d


def trading_on_or_after(d: date) -> date:
    while not is_trading_day(d):
        d += ONE_DAY
    return d


def prev_trading_day(d: date) -> date:
    return trading_on_or_before(d - ONE_DAY)


def trading_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += ONE_DAY
    return out


def rebalances_on(freq: str, d: date) -> bool:
    """First trading day of a new week/month/quarter (mirrors the web's ``rebalancesOn``)."""
    if not is_trading_day(d):
        return False
    if freq == "daily":
        return True
    prev = prev_trading_day(d)
    if freq == "weekly":
        return prev < d - timedelta(days=d.weekday())
    if freq == "monthly":
        return prev.month != d.month
    if freq == "quarterly":
        return (prev.month - 1) // 3 != (d.month - 1) // 3
    return False


# The run date anchors the whole story so a re-seed is always current.
TODAY = datetime.now(ET).date()
SESSION_DAY = trading_on_or_before(TODAY)
PREV_DAY = prev_trading_day(SESSION_DAY)


def ago(days: int) -> date:
    """The first trading day on or after ``days`` calendar days before the session day."""
    return trading_on_or_after(SESSION_DAY - timedelta(days=days))


def days_ago(days: int) -> date:
    return SESSION_DAY - timedelta(days=days)


RR_START = ago(168)
AW_START = ago(105)
TM_START = ago(69)
MS_START = ago(42)
RR_SWITCH = ago(12)
TM_STOP = ago(5)
BT_START = trading_on_or_after(SESSION_DAY - timedelta(days=730))
BARS_START = trading_on_or_after(BT_START - timedelta(days=200))
MARKET_DAYS = trading_days(BARS_START, SESSION_DAY)
DAY_INDEX = {d: i for i, d in enumerate(MARKET_DAYS)}


def password_hash() -> str:
    """bcrypt hash of DEMO_PASSWORD; fresh if bcrypt is present, else the constant."""
    try:
        import bcrypt

        return bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    except ModuleNotFoundError:
        logger.info("bcrypt not installed here; using pre-generated demo1234 hash")
        return _DEMO_PASSWORD_HASH_FALLBACK


def dt(d: date, hour: int = 15, minute: int = 30) -> datetime:
    """UTC datetime at a given UTC wall time on a date."""
    return datetime.combine(d, time(hour, minute), tzinfo=UTC)


def et(d: date, hour: int, minute: int, second: int = 0) -> datetime:
    """UTC instant of a New York wall time on a date."""
    return datetime.combine(d, time(hour, minute, second), tzinfo=ET).astimezone(UTC)


def stable_rng(key: str) -> random.Random:
    """Deterministic RNG seeded from a stable SHA-256 of ``key`` (not ``hash``,
    whose salt varies run-to-run)."""
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big"))


def event_id_for(key: str) -> UUID:
    """Deterministic ledger ``event_id`` from a stable key, the same derivation as
    the real ingestion ``_event_id_from_client_order_id`` (sha256[:16])."""
    return UUID(bytes=hashlib.sha256(key.encode()).digest()[:16])


# Price paths

# Anchor keys → story dates. Each symbol's path is a correlated random walk bent
# (piecewise-linearly in log space) to pass exactly through its anchor prices.
ANCHOR_DATES: dict[str, date] = {
    "start": BARS_START,
    "bt": BT_START,
    "y1": ago(550),
    "y2": ago(365),
    "y3": ago(250),
    "rr": RR_START,
    "aw": AW_START,
    "tm": TM_START,
    "ms": MS_START,
    "sw": RR_SWITCH,
    "stop": TM_STOP,
    "prev": PREV_DAY,
    "T": SESSION_DAY,
}

# symbol → (annual vol, market beta, anchor prices)
PATHS: dict[str, tuple[float, float, dict[str, float]]] = {
    "SPY": (
        0.16,
        1.0,
        {
            "start": 470,
            "bt": 499,
            "y1": 527,
            "y2": 548,
            "y3": 535,
            "rr": 552,
            "aw": 571,
            "tm": 583,
            "ms": 590,
            "sw": 598,
            "stop": 603,
            "prev": 608.2,
            "T": 612.0,
        },
    ),
    "VTI": (
        0.16,
        1.0,
        {
            "start": 236,
            "bt": 249.5,
            "y1": 262,
            "y2": 272,
            "y3": 266,
            "rr": 271,
            "aw": 279,
            "tm": 284,
            "ms": 289,
            "sw": 297,
            "stop": 299,
            "prev": 300.4,
            "T": 302.0,
        },
    ),
    "QQQ": (
        0.20,
        1.15,
        {
            "start": 380,
            "bt": 406,
            "y1": 430,
            "y2": 452,
            "y3": 440,
            "rr": 462,
            "aw": 486,
            "tm": 503,
            "ms": 515,
            "sw": 531,
            "stop": 507,
            "prev": 522.5,
            "T": 528.0,
        },
    ),
    "IWM": (
        0.22,
        1.1,
        {
            "start": 200,
            "bt": 211,
            "y1": 216,
            "y2": 220,
            "y3": 205,
            "rr": 214,
            "aw": 222,
            "tm": 228,
            "ms": 232,
            "sw": 236,
            "stop": 233,
            "prev": 234.2,
            "T": 236.0,
        },
    ),
    "EFA": (
        0.15,
        0.8,
        {"start": 73, "bt": 76.5, "y1": 79, "y2": 82, "y3": 81, "rr": 82.5, "ms": 85.5, "T": 88.1},
    ),
    "BND": (0.05, -0.05, {"bt": 70.6, "rr": 71.4, "T": 73.4}),
    "BIL": (0.005, 0.0, {"bt": 91.2, "T": 91.6}),
    "TLT": (
        0.14,
        -0.25,
        {"bt": 96.3, "rr": 88.5, "aw": 87.2, "sw": 89.6, "prev": 90.10, "T": 90.55},
    ),
    "VGLT": (0.13, -0.25, {"bt": 61.3, "rr": 56.2, "aw": 55.0, "prev": 57.98, "T": 58.20}),
    "IEF": (0.07, -0.1, {"bt": 93.3, "aw": 94.0, "prev": 96.1, "T": 96.4}),
    "GLD": (
        0.16,
        0.05,
        {"bt": 155.0, "rr": 212, "aw": 203, "sw": 243.2, "prev": 246.40, "T": 248.40},
    ),
    "DBC": (0.17, 0.35, {"bt": 22.9, "aw": 22.7, "prev": 23.3, "T": 23.4}),
    "SMH": (
        0.30,
        1.4,
        {
            "bt": 173,
            "rr": 232,
            "aw": 252,
            "tm": 262,
            "ms": 281,
            "sw": 270,
            "stop": 240,
            "prev": 262,
            "T": 268,
        },
    ),
    "XLK": (
        0.22,
        1.2,
        {
            "bt": 168,
            "y2": 190,
            "rr": 214,
            "aw": 236,
            "tm": 246,
            "ms": 255,
            "sw": 251,
            "stop": 232,
            "prev": 248.5,
            "T": 252.0,
        },
    ),
    "XLC": (0.18, 1.0, {"bt": 74, "y2": 84, "rr": 96, "ms": 112, "prev": 117.4, "T": 118.9}),
    "XLI": (0.16, 0.95, {"bt": 118, "y2": 127, "rr": 138, "ms": 157, "prev": 162.6, "T": 164.0}),
    "XLY": (0.19, 1.1, {"bt": 196, "rr": 205, "ms": 214, "T": 219}),
    "XLF": (0.17, 1.0, {"bt": 44.5, "rr": 50, "ms": 52.5, "T": 53.5}),
    "XLE": (0.22, 0.6, {"bt": 92, "rr": 88, "ms": 86, "T": 84}),
    "XLB": (0.17, 0.9, {"bt": 88, "rr": 90, "ms": 92, "T": 93}),
    "XLV": (0.14, 0.6, {"bt": 148, "rr": 142, "ms": 145, "T": 147}),
    "XLP": (0.11, 0.4, {"bt": 79, "rr": 82, "ms": 83, "T": 82.5}),
    "XLU": (0.15, 0.4, {"bt": 70, "rr": 78, "ms": 83.5, "T": 84}),
    "XLRE": (0.18, 0.8, {"bt": 40.5, "rr": 41.5, "ms": 43, "T": 43.8}),
    # Wider universe so template and copilot backtests find bars too.
    "AAPL": (0.25, 1.2, {"bt": 222, "T": 251}),
    "BNDX": (0.05, 0.0, {"bt": 48.6, "T": 49.2}),
    "DBMF": (0.12, 0.1, {"bt": 27, "T": 28.6}),
    "EDV": (0.18, -0.3, {"bt": 76, "T": 70.5}),
    "LQD": (0.08, 0.1, {"bt": 107.5, "T": 110.2}),
    "MINT": (0.01, 0.0, {"bt": 100.2, "T": 100.6}),
    "PDBC": (0.17, 0.35, {"bt": 13.4, "T": 14.1}),
    "SGOV": (0.005, 0.0, {"bt": 100.4, "T": 100.6}),
    "SHY": (0.02, 0.0, {"bt": 81.9, "T": 82.7}),
    "TIP": (0.06, 0.05, {"bt": 108.2, "T": 110.4}),
    "UNG": (0.45, 0.2, {"bt": 15.5, "T": 13.6}),
    "USFR": (0.005, 0.0, {"bt": 50.3, "T": 50.5}),
    "USO": (0.32, 0.4, {"bt": 78, "T": 74.5}),
    "VEA": (0.15, 0.8, {"bt": 49.5, "T": 56.6}),
    "VGIT": (0.05, -0.1, {"bt": 58.4, "T": 60.1}),
    "VNQ": (0.19, 0.85, {"bt": 87, "T": 92.5}),
    "VNQI": (0.17, 0.7, {"bt": 43.5, "T": 47.1}),
    "VWO": (0.18, 0.8, {"bt": 43.2, "T": 48.9}),
}

MARKET_VOL = 0.15


def _build_prices() -> dict[str, list[Decimal]]:
    n = len(MARKET_DAYS)
    daily_market = MARKET_VOL / math.sqrt(252.0)
    mrng = stable_rng("market11")
    market = [mrng.gauss(0.0, daily_market) for _ in range(n)]
    out: dict[str, list[Decimal]] = {}
    for symbol, (vol, beta, anchors) in PATHS.items():
        rng = stable_rng(f"path:{symbol}")
        idio = math.sqrt(max(vol**2 - (beta * MARKET_VOL) ** 2, 0.0004)) / math.sqrt(252.0)
        walk = [0.0]
        for i in range(1, n):
            walk.append(walk[-1] + beta * market[i] + rng.gauss(0.0, idio))
        pins = sorted({DAY_INDEX[ANCHOR_DATES[k]]: math.log(p) for k, p in anchors.items()}.items())
        corr = [0.0] * n
        for i in range(n):
            if i <= pins[0][0]:
                corr[i] = pins[0][1] - walk[pins[0][0]]
            elif i >= pins[-1][0]:
                corr[i] = pins[-1][1] - walk[pins[-1][0]]
            else:
                k = next(j for j in range(1, len(pins)) if pins[j][0] >= i)
                (i0, v0), (i1, v1) = pins[k - 1], pins[k]
                c0, c1 = v0 - walk[i0], v1 - walk[i1]
                corr[i] = c0 + (c1 - c0) * (i - i0) / (i1 - i0)
        out[symbol] = [
            Decimal(str(round(math.exp(w + c), 2))) for w, c in zip(walk, corr, strict=True)
        ]
    return out


PRICES = _build_prices()


def price(symbol: str, d: date) -> Decimal:
    """Close on ``d`` (or the last trading day before it)."""
    return PRICES[symbol][DAY_INDEX[trading_on_or_before(d)]]


def intraday_price(symbol: str, at: datetime) -> Decimal:
    """A mark during the session day, moving from the prior close toward the close."""
    local = at.astimezone(ET)
    d = trading_on_or_before(local.date())
    minutes = local.hour * 60 + local.minute
    frac = Decimal(str(max(0.0, min(1.0, (minutes - 570) / 390))))
    prev = price(symbol, prev_trading_day(d))
    return (prev + (price(symbol, d) - prev) * frac).quantize(CENT)


def trailing_return(symbol: str, d: date, n: int) -> float:
    i = DAY_INDEX[d]
    series = PRICES[symbol]
    return float(series[i] / series[max(0, i - n)]) - 1.0


def trailing_vol(symbol: str, d: date, n: int) -> float:
    i = DAY_INDEX[d]
    series = [float(p) for p in PRICES[symbol][max(0, i - n) : i + 1]]
    rets = [math.log(b / a) for a, b in zip(series, series[1:], strict=False)]
    return float(np.std(rets)) if len(rets) > 1 else 0.01


# Strategy rules (targets drive both the session simulations and the backtests)

Targets = dict[str, float]


def top_by_momentum(universe: list[str], d: date, n: int, k: int) -> Targets:
    ranked = sorted(universe, key=lambda s: trailing_return(s, d, n), reverse=True)[:k]
    return {s: 1.0 / k for s in ranked}


SECTORS = ["XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLB", "XLV", "XLP", "XLU", "XLRE"]


def recession_radar(d: date) -> Targets:
    if d >= RR_SWITCH:
        return {"TLT": 0.6, "GLD": 0.4}
    return {"VTI": 1 / 3, "QQQ": 1 / 3, "IWM": 1 / 3}


def risk_parity(d: date) -> Targets:
    inv = {s: 1.0 / trailing_vol(s, d, 60) for s in ("SPY", "TLT", "GLD", "DBC")}
    total = sum(inv.values())
    return {s: v / total for s, v in inv.items()}


def dual_momentum(lookback: int) -> Callable[[date], Targets]:
    def rule(d: date) -> Targets:
        if trailing_return("SPY", d, lookback) > 0:
            return top_by_momentum(["SPY", "EFA"], d, lookback, 1)
        return {"BND": 1.0}

    return rule


RULES: dict[tuple[str, int], Callable[[date], Targets]] = {
    ("all-weather", 1): lambda d: {"VTI": 0.3, "TLT": 0.4, "IEF": 0.15, "GLD": 0.075, "DBC": 0.075},
    ("all-weather", 2): lambda d: {
        "VTI": 0.3,
        "VGLT": 0.4,
        "IEF": 0.15,
        "GLD": 0.075,
        "DBC": 0.075,
    },
    ("recession-radar", 0): recession_radar,
    ("momentum-sectors", 0): lambda d: top_by_momentum(SECTORS, d, 90, 3),
    ("tech-momentum-rotation", 0): lambda d: top_by_momentum(["QQQ", "SMH", "XLK"], d, 20, 2),
    ("risk-parity", 0): risk_parity,
    ("dual-momentum", 1): dual_momentum(252),
    ("dual-momentum", 2): dual_momentum(126),
}


def rule_for(strategy_id: str, version: int) -> Callable[[date], Targets]:
    return RULES.get((strategy_id, version)) or RULES[(strategy_id, 0)]


# Trade plan (drives ledger fills, orders, positions)


@dataclass(frozen=True)
class Fill:
    at: datetime
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    price: Decimal
    reason: str = "Rebalance to target weights"
    fees: Decimal = ZERO


@dataclass(frozen=True)
class Dividend:
    at: datetime
    symbol: str
    amount: Decimal


@dataclass
class SessionPlan:
    key: str  # short id used to build client_order_ids
    strategy_id: str
    live: bool
    allocated: Decimal
    start: date
    color: str
    invest: Decimal  # fraction of equity a rebalance puts to work
    band: Decimal  # skip a trade smaller than this fraction of equity
    stop: date | None = None
    today: tuple[Fill, ...] = ()
    fills: list[Fill] = field(default_factory=list)
    dividends: list[Dividend] = field(default_factory=list)


SESSION_PLANS: list[SessionPlan] = [
    SessionPlan(
        key="aw",
        strategy_id="all-weather",
        live=True,
        allocated=Decimal("45140.00"),
        start=AW_START,
        color="#0ea5e9",
        invest=Decimal("0.95"),
        band=Decimal("0.004"),
        today=(
            Fill(
                et(SESSION_DAY, 9, 45, 12),
                "VGLT",
                "buy",
                Decimal("31"),
                Decimal("58.12"),
                "Drift past the band: top up VGLT",
            ),
        ),
    ),
    SessionPlan(
        key="rr",
        strategy_id="recession-radar",
        live=False,
        allocated=Decimal("28385.00"),
        start=RR_START,
        color="#10b981",
        invest=Decimal("0.94"),
        band=Decimal("0.02"),
        today=(
            Fill(
                et(SESSION_DAY, 10, 31, 2),
                "GLD",
                "sell",
                Decimal("9"),
                Decimal("247.86"),
                "Drift past the band: trim GLD",
            ),
            Fill(
                et(SESSION_DAY, 10, 31, 6),
                "TLT",
                "buy",
                Decimal("42"),
                Decimal("90.41"),
                "Drift past the band: top up TLT",
            ),
        ),
    ),
    SessionPlan(
        key="tm",
        strategy_id="tech-momentum-rotation",
        live=False,
        allocated=Decimal("26817.00"),
        start=TM_START,
        stop=TM_STOP,
        color="#8b5cf6",
        invest=Decimal("0.98"),
        band=Decimal("0.015"),
    ),
    SessionPlan(
        key="ms",
        strategy_id="momentum-sectors",
        live=False,
        allocated=Decimal("21453.00"),
        start=MS_START,
        color="#f59e0b",
        invest=Decimal("0.93"),
        band=Decimal("0.004"),
    ),
]

# Idle paper cash left in Unallocated; the e2e trading journeys fund a sleeve from it.
PAPER_FREE_CASH = Decimal("5000.00")

# Monthly distribution yield credited on the first trading day of each month.
BOND_YIELDS: dict[str, Decimal] = {
    "TLT": Decimal("0.0035"),
    "VGLT": Decimal("0.0033"),
    "IEF": Decimal("0.0030"),
}

STRATEGY_ORDER = [
    "all-weather",
    "recession-radar",
    "momentum-sectors",
    "tech-momentum-rotation",
    "risk-parity",
    "dual-momentum",
    "pullback-buyer",
]

# Days before the session day each version was saved.
VERSION_DAYS: dict[str, list[int]] = {
    "all-weather": [180, 112],
    "recession-radar": [175, 120, 14],
    "momentum-sectors": [60, 52, 47, 44, 27],
    "tech-momentum-rotation": [120, 100, 85, 74],
    "risk-parity": [48],
    "dual-momentum": [12, 3],
    "pullback-buyer": [2],
}

STRATEGY_STATUS: dict[str, int] = {
    "all-weather": strategy_pb2.STRATEGY_STATUS_ACTIVE,
    "recession-radar": strategy_pb2.STRATEGY_STATUS_ACTIVE,
    "momentum-sectors": strategy_pb2.STRATEGY_STATUS_ACTIVE,
    "tech-momentum-rotation": strategy_pb2.STRATEGY_STATUS_PAUSED,
    "risk-parity": strategy_pb2.STRATEGY_STATUS_ACTIVE,
    "dual-momentum": strategy_pb2.STRATEGY_STATUS_ACTIVE,
    "pullback-buyer": strategy_pb2.STRATEGY_STATUS_DRAFT,
}


def _floor_shares(amount: Decimal, px: Decimal) -> Decimal:
    return (amount / px).quantize(Decimal("1"), rounding=ROUND_DOWN) if px > 0 else ZERO


def simulate_session(plan: SessionPlan, rebalance: str, version: int) -> None:
    """Integer-share fills for one session: an initial allocation, drift-banded
    rebalances on its schedule, a close-to-cash on stop, then today's fills."""
    rule = rule_for(plan.strategy_id, version)
    cash = plan.allocated
    held: dict[str, Decimal] = {}
    previous: Targets = {}
    last = plan.stop or PREV_DAY
    for d in trading_days(plan.start, last):
        if d != plan.start and prev_trading_day(d).month != d.month:
            for symbol in sorted(held):
                if symbol in BOND_YIELDS:
                    amount = (held[symbol] * price(symbol, d) * BOND_YIELDS[symbol]).quantize(CENT)
                    plan.dividends.append(Dividend(et(d, 12, 0), symbol, amount))
                    cash += amount
        if d == plan.stop:
            for i, symbol in enumerate(sorted(held)):
                px = price(symbol, d)
                qty = held.pop(symbol)
                plan.fills.append(
                    Fill(
                        et(d, 15, 50, 5 + 3 * i),
                        symbol,
                        "sell",
                        qty,
                        px,
                        "Session stopped: closing to cash",
                    )
                )
                cash += qty * px
            break
        initial = d == plan.start
        if not initial and not rebalances_on(rebalance, d):
            continue
        targets = rule(d)
        if initial:
            reason = "Initial allocation"
        elif set(targets) != set(previous):
            reason = (
                "SPY RSI(14) above 70: rotate to TLT and GLD"
                if plan.strategy_id == "recession-radar"
                else "Momentum ranking changed"
            )
        else:
            reason = "Rebalance to target weights"
        previous = targets
        prices = {s: price(s, d) for s in set(held) | set(targets)}
        equity = cash + sum((held[s] * prices[s] for s in held), ZERO)
        desired = {
            s: _floor_shares(equity * plan.invest * Decimal(str(w)), prices[s])
            for s, w in targets.items()
        }
        sells: list[tuple[str, Decimal]] = []
        buys: list[tuple[str, Decimal]] = []
        for s in sorted(set(held) | set(desired)):
            diff = desired.get(s, ZERO) - held.get(s, ZERO)
            if diff == 0:
                continue
            kept = desired.get(s, ZERO) > 0
            if not initial and kept and abs(diff) * prices[s] < plan.band * equity:
                continue
            (sells if diff < 0 else buys).append((s, abs(diff)))
        base = et(d, 10, 5) if initial else et(d, 15, 50)
        n = 0
        for s, qty in sells:
            n += 1
            plan.fills.append(
                Fill(base + timedelta(seconds=5 + 3 * n), s, "sell", qty, prices[s], reason)
            )
            cash += qty * prices[s]
            held[s] = held[s] - qty
            if held[s] == 0:
                del held[s]
        for s, qty in buys:
            qty = min(qty, _floor_shares(cash, prices[s]))
            if qty <= 0:
                continue
            n += 1
            plan.fills.append(
                Fill(base + timedelta(seconds=5 + 3 * n), s, "buy", qty, prices[s], reason)
            )
            cash -= qty * prices[s]
            held[s] = held.get(s, ZERO) + qty
    if plan.stop is None:
        for f in plan.today:
            if f.side == "sell":
                if held.get(f.symbol, ZERO) < f.qty:
                    raise RuntimeError(f"{plan.key}: today's sale of {f.symbol} exceeds holdings")
                held[f.symbol] -= f.qty
                cash += f.qty * f.price
            else:
                if cash < f.qty * f.price:
                    raise RuntimeError(f"{plan.key}: not enough cash for today's {f.symbol} buy")
                held[f.symbol] = held.get(f.symbol, ZERO) + f.qty
                cash -= f.qty * f.price
            plan.fills.append(f)


@dataclass(frozen=True)
class RunSpec:
    version: int
    completed: datetime
    end: date


def _completed_run(version: int, days: int, hour: int = 20, minute: int = 10) -> RunSpec:
    at = et(days_ago(days), hour, minute)
    return RunSpec(version, at, prev_trading_day(days_ago(days)))


# Running strategies get a fresh run after yesterday's close, so each session has
# a completed backtest that covers its own dates.
BACKTEST_RUNS: dict[str, list[RunSpec]] = {
    "all-weather": [_completed_run(1, 179), RunSpec(2, et(PREV_DAY, 18, 40), PREV_DAY)],
    "recession-radar": [_completed_run(1, 174), RunSpec(3, et(PREV_DAY, 18, 42), PREV_DAY)],
    "momentum-sectors": [_completed_run(1, 59), RunSpec(5, et(PREV_DAY, 18, 44), PREV_DAY)],
    "tech-momentum-rotation": [_completed_run(4, 74)],
    "risk-parity": [_completed_run(1, 48)],
    "dual-momentum": [_completed_run(1, 7)],
}

# (win rate, profit factor, trade count) for each strategy's synthesized trade log.
TRADE_STATS: dict[str, tuple[float, float, int]] = {
    "all-weather": (0.58, 1.66, 88),
    "recession-radar": (0.60, 1.90, 64),
    "momentum-sectors": (0.48, 1.28, 156),
    "tech-momentum-rotation": (0.47, 1.35, 140),
    "risk-parity": (0.60, 1.91, 120),
    "dual-momentum": (0.55, 1.60, 40),
}
BT_INITIAL = 25000.0


@dataclass(frozen=True)
class BacktestSpec:
    strategy_id: str
    win_rate: float
    profit_factor: float
    trades: int


def backtest_curve(
    rule: Callable[[date], Targets], rebalance: str, start: date, end: date, initial: float
) -> list[tuple[date, float]]:
    """Fractional-share run of a rule over the price paths."""
    units: dict[str, float] = {}
    cash = initial
    out: list[tuple[date, float]] = []
    for i, d in enumerate(trading_days(start, end)):
        if i == 0 or rebalances_on(rebalance, d):
            equity = cash + sum(u * float(price(s, d)) for s, u in units.items())
            weights = rule(d)
            units = {s: equity * w / float(price(s, d)) for s, w in weights.items()}
            cash = equity * (1.0 - sum(weights.values()))
        out.append((d, cash + sum(u * float(price(s, d)) for s, u in units.items())))
    return out


# In-memory ledger event mirror (for folding the equity curve)


@dataclass
class SeedEvent:
    """Duck-types ``LedgerEventLike`` for the pure ``fold`` kernel."""

    event_type: str
    data: dict[str, str]
    sequence: int
    occurred_at: datetime
    event_id: str = ""


# Engine-faithful metric math (mirrors services/backtest/src/engine/metrics.py
# and engine/benchmarks.py exactly, so synthesized results match a real run).
# Reimplemented here — the backtest service package is not importable inside the
# portfolio container the seed runs in — but the formulas (and numpy ddof
# conventions: std/var ddof=0, cov ddof=1) are identical.


def bt_returns(
    equity: list[float], initial: float, num_days: int
) -> tuple[float, float, list[float]]:
    """metrics.calculate_returns: total return, annualized return, daily returns."""
    if not equity:
        return 0.0, 0.0, []
    arr = np.array(equity, dtype=float)
    final = float(arr[-1])
    total_return = (final - initial) / initial if initial > 0 else 0.0
    if num_days <= 0:
        annual_return = 0.0
    elif 1 + total_return > 0:
        annual_return = ((1 + total_return) ** (252 / num_days)) - 1
    else:
        annual_return = -1.0
    if len(arr) > 1:
        prev = arr[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            daily = np.where(prev > 0, np.diff(arr) / prev, 0.0)
        daily = np.nan_to_num(daily, nan=0.0, posinf=0.0, neginf=0.0)
        return total_return, annual_return, [float(x) for x in daily]
    return total_return, annual_return, []


def bt_sharpe(daily: np.ndarray, risk_free_rate: float = 0.02) -> float:
    """metrics.calculate_sharpe_ratio."""
    if len(daily) == 0 or np.std(daily) == 0:
        return 0.0
    excess = daily - risk_free_rate / 252
    return float(np.sqrt(252) * np.mean(excess) / np.std(daily))


def bt_sortino(daily: np.ndarray, risk_free_rate: float = 0.02) -> float:
    """metrics.calculate_sortino_ratio."""
    if len(daily) == 0:
        return 0.0
    negative = daily[daily < 0]
    if len(negative) == 0 or np.std(negative) == 0:
        return 0.0
    return float(np.sqrt(252) * np.mean(daily) / np.std(negative))


def bt_max_drawdown(equity: np.ndarray) -> tuple[float, int]:
    """metrics.calculate_max_drawdown: (positive max drawdown fraction, duration bars)."""
    if len(equity) == 0:
        return 0.0, 0
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak > 0, (peak - equity) / peak, 0.0)
    drawdown = np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0)
    max_dd = float(np.max(drawdown)) if drawdown.size else 0.0
    duration = current = 0
    for dd in drawdown:
        if dd > 0:
            current += 1
            duration = max(duration, current)
        else:
            current = 0
    return max_dd, duration


def bt_monthly_returns(curve: list[tuple[datetime, float]], initial: float) -> dict[str, float]:
    """metrics.calculate_monthly_returns."""
    if not curve:
        return {}
    by_month: dict[str, list[tuple[datetime, float]]] = {}
    for ts, eq in curve:
        by_month.setdefault(ts.strftime("%Y-%m"), []).append((ts, eq))
    out: dict[str, float] = {}
    prev_end = initial
    for month in sorted(by_month):
        month_end = by_month[month][-1][1]
        out[month] = (month_end - prev_end) / prev_end if prev_end > 0 else 0.0
        prev_end = month_end
    return out


def bt_align_daily_returns(
    strategy_curve: list[tuple[datetime, float]],
    benchmark_bars: list[tuple[datetime, float]],
) -> tuple[np.ndarray, np.ndarray]:
    """benchmarks.align_daily_returns: date-joined day-over-day returns."""

    def by_date(points: list[tuple[datetime, float]]) -> dict[date, float]:
        daily: list[tuple[date, float]] = []
        for ts, val in points:
            d = ts.date()
            if daily and daily[-1][0] == d:
                daily[-1] = (d, val)
            else:
                daily.append((d, val))
        returns: dict[date, float] = {}
        for (_, prev_val), (d, val) in zip(daily, daily[1:], strict=False):
            if prev_val > 0:
                returns[d] = (val - prev_val) / prev_val
        return returns

    strat = by_date(strategy_curve)
    bench = by_date(benchmark_bars)
    common = sorted(set(strat) & set(bench))
    return (
        np.array([strat[d] for d in common]),
        np.array([bench[d] for d in common]),
    )


def bt_alpha_beta(
    strat: np.ndarray, bench: np.ndarray, risk_free_rate: float = 0.02
) -> tuple[float | None, float | None]:
    """benchmarks.calculate_alpha_beta (annualized alpha; None when undefined)."""
    if len(strat) < 2 or len(bench) < 2:
        return None, None
    n = min(len(strat), len(bench))
    strat, bench = strat[:n], bench[:n]
    variance = np.var(bench)
    if variance <= 0:
        return None, None
    beta = np.cov(strat, bench)[0, 1] / variance
    alpha = np.mean(strat) * 252 - (risk_free_rate + beta * (np.mean(bench) * 252 - risk_free_rate))
    return float(alpha), float(beta)


def bt_information_ratio(strat: np.ndarray, bench: np.ndarray) -> float | None:
    """benchmarks.calculate_information_ratio (None when undefined)."""
    if len(strat) < 2 or len(bench) < 2:
        return None
    n = min(len(strat), len(bench))
    active = strat[:n] - bench[:n]
    tracking_error = np.std(active)
    if tracking_error <= 0:
        return None
    return float(np.sqrt(252) * np.mean(active) / tracking_error)


@dataclass(frozen=True)
class SynthTrades:
    """Synthesized trades plus counts derived FROM them, so ``total_trades`` /
    ``winning`` / ``losing`` / ``win_rate`` / ``profit_factor`` can never disagree
    with the stored ``trades`` array (engine convention: win = pnl > 0)."""

    trades: list[dict[str, object]]
    total: int
    winning: int
    losing: int
    win_rate: float
    profit_factor: float | None
    avg_trade_return: float


@dataclass(frozen=True)
class _RawTrade:
    """A pre-scaling trade draw: realistic entry/qty/dates + a signed ``natural``
    P&L. Winners and losers are later scaled independently so the list's Σ(pnl)
    hits the curve's final-equity gain (see ``_synth_trades``)."""

    symbol: str
    entry: float
    qty: int
    win: bool
    natural: float  # entry * pct * qty, signed
    entry_day: date
    exit_day: date


# Seeder


def load_strategy_data() -> dict[str, dict[str, object]]:
    raw = json.loads((DATA_DIR / "strategies.json").read_text())
    return {row["id"]: row for row in raw}


def latest_version(data: dict[str, object]) -> dict[str, object]:
    versions: list[dict[str, object]] = data["versions"]  # type: ignore[assignment]
    return versions[-1]


def plan_sessions(strategy_data: dict[str, dict[str, object]]) -> None:
    for plan in SESSION_PLANS:
        current = latest_version(strategy_data[plan.strategy_id])
        simulate_session(plan, str(current["rebalance"]), int(current["version"]))  # type: ignore[call-overload]


@dataclass
class AccountState:
    key: str
    account: Account
    credentials_id: UUID
    unallocated: Sleeve
    events: list[SeedEvent] = field(default_factory=list)


class Seeder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.writer = LedgerWriter(db)
        self.counts: dict[str, int] = {}
        self._seq = 0

    def _bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    # purge

    async def purge_existing(self) -> None:
        tenant_id = await self.db.scalar(
            text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": DEMO_SLUG}
        )
        if tenant_id is None:
            logger.info("no existing demo tenant; fresh seed")
            return
        logger.info("existing demo tenant %s found — purging tenant-scoped rows", tenant_id)
        statements = [
            "DELETE FROM notifications WHERE tenant_id = :t",
            "DELETE FROM alerts WHERE tenant_id = :t",
            "DELETE FROM notification_channels WHERE tenant_id = :t",
            "DELETE FROM webhooks WHERE tenant_id = :t",
            "DELETE FROM tool_call_logs WHERE tenant_id = :t",
            "DELETE FROM pending_artifacts WHERE tenant_id = :t",
            "DELETE FROM agent_memory_facts WHERE tenant_id = :t",
            "DELETE FROM agent_messages WHERE tenant_id = :t",
            "DELETE FROM agent_sessions WHERE tenant_id = :t",
            "DELETE FROM ledger_sleeve_snapshots WHERE tenant_id = :t",
            "DELETE FROM ledger_events WHERE tenant_id = :t",
            "DELETE FROM ledger_lots WHERE tenant_id = :t",
            "DELETE FROM ledger_sleeves WHERE tenant_id = :t",
            "DELETE FROM ledger_accounts WHERE tenant_id = :t",
            "DELETE FROM positions WHERE tenant_id = :t",
            "DELETE FROM orders WHERE tenant_id = :t",
            "DELETE FROM trading_sessions WHERE tenant_id = :t",
            "DELETE FROM backtest_results WHERE backtest_id IN (SELECT id FROM backtests WHERE tenant_id = :t)",
            "DELETE FROM backtests WHERE tenant_id = :t",
            "DELETE FROM strategy_executions WHERE tenant_id = :t",
            "DELETE FROM strategy_versions WHERE tenant_id = :t",
            "DELETE FROM strategies WHERE tenant_id = :t",
            "DELETE FROM invoices WHERE tenant_id = :t",
            "DELETE FROM usage_records WHERE tenant_id = :t",
            "DELETE FROM subscriptions WHERE tenant_id = :t",
            "DELETE FROM payment_methods WHERE tenant_id = :t",
            "DELETE FROM alpaca_credentials WHERE tenant_id = :t",
            "DELETE FROM api_keys WHERE tenant_id = :t",
            "DELETE FROM users WHERE tenant_id = :t",
            "DELETE FROM tenants WHERE id = :t",
        ]
        for stmt in statements:
            await self.db.execute(text(stmt), {"t": tenant_id})

    # identity

    async def seed_identity(self) -> None:
        self.tenant = Tenant(
            id=DEMO_TENANT_ID,
            name=TENANT_NAME,
            slug=DEMO_SLUG,
            is_active=True,
            settings={"onboarded": True, "theme": "dark"},
            created_at=dt(TENANT_CREATED, 14, 0),
        )
        self.db.add(self.tenant)
        await self.db.flush()
        self.tenant_id = self.tenant.id
        self._bump("tenants")

        self.user = User(
            id=DEMO_USER_ID,
            tenant_id=self.tenant_id,
            email=DEMO_EMAIL,
            password_hash=password_hash(),
            first_name=FIRST_NAME,
            last_name=LAST_NAME,
            avatar_url=DEMO_AVATAR_URL,
            role="admin",
            is_active=True,
            is_verified=True,
            last_login=et(SESSION_DAY, 8, 15),
            settings={"default_view": "dashboard"},
            created_at=dt(TENANT_CREATED, 14, 0),
        )
        self.db.add(self.user)
        await self.db.flush()
        self.user_id = self.user.id
        self._bump("users")

        self.paper_creds = AlpacaCredentials(
            id=uuid4(),
            tenant_id=self.tenant_id,
            name="Alpaca Paper (Demo)",
            api_key_encrypted=encrypt_value("PKDEMOSOFIARIVERA0001"),
            api_secret_encrypted=encrypt_value("demoSecretSofiaRivera00000000000000000001"),
            is_paper=True,
            is_active=True,
            created_at=et(RR_START - timedelta(days=3), 19, 30),
        )
        self.live_creds = AlpacaCredentials(
            id=uuid4(),
            tenant_id=self.tenant_id,
            name="Alpaca Live (Demo)",
            api_key_encrypted=encrypt_value("AKDEMOSOFIARIVERA0001"),
            api_secret_encrypted=encrypt_value("demoLiveSecretSofiaRivera000000000000001"),
            is_paper=False,
            is_active=True,
            created_at=et(AW_START - timedelta(days=3), 19, 30),
        )
        self.db.add_all([self.paper_creds, self.live_creds])
        await self.db.flush()
        self._bump("alpaca_credentials", 2)

    # billing

    async def seed_billing(self) -> None:
        pro = await self._get_or_create_plan(
            name="pro",
            display_name="Pro",
            description="For serious individual traders: unlimited strategies, live paper trading, AI copilot.",
            tier=billing_pb2.PLAN_TIER_PRO,
            price_monthly=Decimal("49.00"),
            price_yearly=Decimal("490.00"),
            # Placeholder Stripe price ids so checkout/subscribe reach the Stripe
            # API (stripe-mock locally); the paid path needs a non-empty price id.
            stripe_price_id_monthly="price_demo_pro_monthly",
            stripe_price_id_yearly="price_demo_pro_yearly",
            features={"live_paper": True, "ai_copilot": True, "backtests": True},
            # Keys must match billing_service DEFAULT_PLANS: the servicer reads
            # limits["live_strategies"] for BOTH max_strategies and max_live_sessions.
            limits={"backtests_per_month": None, "live_strategies": 5, "api_calls_per_day": 100000},
            trial_days=14,
            sort_order=3,
        )
        await self._get_or_create_plan(
            name="free",
            display_name="Free",
            description="Explore LlamaTrade: build strategies and run backtests.",
            tier=billing_pb2.PLAN_TIER_FREE,
            price_monthly=Decimal("0.00"),
            price_yearly=Decimal("0.00"),
            features={"backtests": True},
            limits={"backtests_per_month": 5, "live_strategies": 0, "api_calls_per_day": 1000},
            trial_days=0,
            sort_order=1,
        )

        # Monthly cycle anchored on the 20th, when the 14-day trial converted.
        anchor = date(2026, 1, 20)
        cycles: list[date] = []
        d = anchor
        while d <= TODAY:
            cycles.append(d)
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 20)
        period_start, period_end = cycles[-1], d

        sub = Subscription(
            id=uuid4(),
            tenant_id=self.tenant_id,
            plan_id=pro.id,
            status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
            billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
            stripe_subscription_id="sub_demo_sofiarivera",
            stripe_customer_id="cus_demo_sofiarivera",
            current_period_start=dt(period_start, 0, 0),
            current_period_end=dt(period_end, 0, 0),
            cancel_at_period_end=False,
            trial_start=dt(TENANT_CREATED, 0, 0),
            trial_end=dt(TENANT_CREATED + timedelta(days=14), 0, 0),
            created_at=dt(TENANT_CREATED, 14, 45),
        )
        self.db.add(sub)
        await self.db.flush()
        self._bump("subscriptions")

        self.db.add(
            PaymentMethod(
                id=uuid4(),
                tenant_id=self.tenant_id,
                stripe_payment_method_id="pm_demo_sofiarivera_visa",
                stripe_customer_id="cus_demo_sofiarivera",
                type="card",
                card_brand="visa",
                card_last4="4242",
                card_exp_month=11,
                card_exp_year=2028,
                is_default=True,
                created_at=dt(TENANT_CREATED, 14, 45),
            )
        )
        self._bump("payment_methods")

        amount = Decimal("49.00")
        for i, start in enumerate(cycles):
            end = cycles[i + 1] if i + 1 < len(cycles) else period_end
            desc = "Pro plan, first month" if i == 0 else "Pro plan (monthly)"
            self.db.add(
                Invoice(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    subscription_id=sub.id,
                    stripe_invoice_id=f"in_demo_sofiarivera_{start:%Y%m}",
                    invoice_number=f"LT-{start:%Y}-{100 + i}",
                    status=billing_pb2.INVOICE_STATUS_PAID,
                    amount_due=amount,
                    amount_paid=amount,
                    currency="usd",
                    period_start=dt(start, 0, 0),
                    period_end=dt(end, 0, 0),
                    paid_at=dt(start, 6, 5),
                    line_items=[{"description": desc, "amount": str(amount)}],
                    created_at=dt(start, 6, 0),
                )
            )
            self._bump("invoices")

    async def _get_or_create_plan(self, *, name: str, **kw: object) -> Plan:
        existing = await self.db.scalar(text("SELECT id FROM plans WHERE name = :n"), {"n": name})
        if existing is not None:
            plan = await self.db.get(Plan, existing)
            assert plan is not None
            for key, value in kw.items():  # converge the definition on re-seed
                setattr(plan, key, value)
            return plan
        plan = Plan(id=uuid4(), name=name, is_active=True, **kw)  # type: ignore[arg-type]
        self.db.add(plan)
        await self.db.flush()
        self._bump("plans")
        return plan

    # strategies

    async def seed_strategies(self) -> None:
        self.strategy_data = load_strategy_data()
        self.strategy_rows: dict[str, Strategy] = {}
        for sid in STRATEGY_ORDER:
            data = self.strategy_data[sid]
            versions: list[dict[str, object]] = data["versions"]  # type: ignore[assignment]
            saved = [et(days_ago(n), 11, 0) for n in VERSION_DAYS[sid]]
            strat = Strategy(
                id=uuid5(NAMESPACE_URL, f"llamatrade:demo:strategy:{sid}"),
                tenant_id=self.tenant_id,
                name=str(data["name"]),
                description=str(data["description"]),
                status=STRATEGY_STATUS[sid],
                is_public=False,
                current_version=len(versions),
                created_by=self.user_id,
                created_at=saved[0],
                updated_at=saved[-1],
            )
            self.db.add(strat)
            await self.db.flush()
            self.strategy_rows[sid] = strat
            self._bump("strategies")
            for v, at in zip(versions, saved, strict=True):
                self.db.add(
                    StrategyVersion(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        strategy_id=strat.id,
                        version=int(v["version"]),  # type: ignore[call-overload]
                        config_sexpr=str(v["config_sexpr"]),
                        symbols=v["symbols"],  # type: ignore[arg-type]
                        rebalance=str(v["rebalance"]),
                        changelog=str(v["changelog"]),
                        created_by=self.user_id,
                        created_at=at,
                    )
                )
                self._bump("strategy_versions")

    # ledger identity: one account per Alpaca credential, a sleeve per session

    async def seed_ledger_identity(self) -> None:
        self.accounts: dict[str, AccountState] = {}
        for key, creds, opened in (
            ("paper", self.paper_creds, RR_START),
            ("live", self.live_creds, AW_START),
        ):
            account = Account(
                id=uuid4(),
                tenant_id=self.tenant_id,
                credentials_id=creds.id,
                base_currency="USD",
                created_at=et(opened, 9, 50),
            )
            self.db.add(account)
            await self.db.flush()
            self._bump("ledger_accounts")
            base: dict[SleeveType, Sleeve] = {}
            for kind, name in (
                (SleeveType.UNALLOCATED, "Unallocated"),
                (SleeveType.MANUAL, "Manual"),
                (SleeveType.UNMANAGED, "Unmanaged"),
            ):
                sleeve = Sleeve(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    account_id=account.id,
                    type=kind.value,
                    status=SleeveStatus.ACTIVE.value,
                    name=name,
                    allocated_capital=ZERO,
                    created_at=et(opened, 9, 50),
                )
                self.db.add(sleeve)
                base[kind] = sleeve
            await self.db.flush()
            self._bump("ledger_sleeves", 3)
            self.accounts[key] = AccountState(key, account, creds.id, base[SleeveType.UNALLOCATED])

        self.plan_sleeve: dict[str, Sleeve] = {}
        self.plan_execution: dict[str, StrategyExecution] = {}
        for plan in SESSION_PLANS:
            acct = self.accounts["live" if plan.live else "paper"]
            strat = self.strategy_rows[plan.strategy_id]
            execution = StrategyExecution(
                id=uuid4(),
                tenant_id=self.tenant_id,
                strategy_id=strat.id,
                version=strat.current_version,
                mode=common_pb2.EXECUTION_MODE_LIVE
                if plan.live
                else common_pb2.EXECUTION_MODE_PAPER,
                status=(
                    common_pb2.EXECUTION_STATUS_STOPPED
                    if plan.stop
                    else common_pb2.EXECUTION_STATUS_RUNNING
                ),
                started_at=et(plan.start, 10, 0),
                stopped_at=et(plan.stop, 15, 52) if plan.stop else None,
                allocated_capital=plan.allocated,
                color=plan.color,
                credentials_id=acct.credentials_id,
                created_at=et(plan.start, 9, 55),
            )
            self.db.add(execution)
            await self.db.flush()
            sleeve = Sleeve(
                id=uuid4(),
                tenant_id=self.tenant_id,
                account_id=acct.account.id,
                type=SleeveType.STRATEGY.value,
                status=SleeveStatus.ACTIVE.value,
                name=str(strat.name),
                strategy_execution_id=execution.id,
                allocated_capital=plan.allocated,
                created_at=et(plan.start, 9, 58),
            )
            self.db.add(sleeve)
            await self.db.flush()
            execution.sleeve_id = sleeve.id
            execution.account_id = acct.account.id
            self.plan_sleeve[plan.key] = sleeve
            self.plan_execution[plan.key] = execution
            self._bump("strategy_executions")
            self._bump("ledger_sleeves")

    # ledger events

    async def _append(
        self,
        acct: AccountState,
        event_type: LedgerEventType,
        data: dict[str, str],
        *,
        sleeve_id: UUID | None,
        occurred_at: datetime,
        event_id: UUID,
    ) -> None:
        event, _ = await self.writer.append(
            tenant_id=self.tenant_id,
            account_id=acct.account.id,
            event_type=event_type,
            data=data,
            sleeve_id=sleeve_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )
        self._seq += 1
        acct.events.append(
            SeedEvent(event_type.value, dict(data), int(event.sequence), occurred_at)
        )
        self._bump("ledger_events")

    async def seed_ledger_events(self) -> None:
        """Every economic event, appended in global time order so ledger sequence
        follows ``occurred_at``. Each session is funded by its own deposit and
        allocation; paper Unallocated also keeps ``PAPER_FREE_CASH`` idle."""
        timeline: list[tuple[datetime, int, SessionPlan, object]] = []
        for plan in SESSION_PLANS:
            timeline.append((et(plan.start, 9, 55), 0, plan, "fund"))
            timeline.extend((div.at, 1, plan, div) for div in plan.dividends)
            timeline.extend((f.at, 2, plan, f) for f in plan.fills)
        timeline.sort(key=lambda row: (row[0], row[1], row[2].key))

        self.order_rows: list[tuple[SessionPlan, Order]] = []
        self.pos_realized: dict[tuple[str, str], Decimal] = {}
        self.pos_opened: dict[tuple[str, str], datetime] = {}
        lots: dict[tuple[str, str], list[FifoLot]] = {}
        fill_counter: dict[str, int] = {}

        paper = self.accounts["paper"]
        await self._append(
            paper,
            LedgerEventType.FUNDS_DEPOSITED,
            {"sleeve_id": str(paper.unallocated.id), "amount": str(PAPER_FREE_CASH)},
            sleeve_id=paper.unallocated.id,
            occurred_at=et(RR_START, 9, 50),
            event_id=event_id_for("demo:deposit:paper-float"),
        )
        for at, _, plan, payload in timeline:
            acct = self.accounts["live" if plan.live else "paper"]
            sleeve = self.plan_sleeve[plan.key]
            if payload == "fund":
                await self._append(
                    acct,
                    LedgerEventType.FUNDS_DEPOSITED,
                    {"sleeve_id": str(acct.unallocated.id), "amount": str(plan.allocated)},
                    sleeve_id=acct.unallocated.id,
                    occurred_at=at,
                    event_id=event_id_for(f"demo:deposit:{plan.key}"),
                )
                await self._append(
                    acct,
                    LedgerEventType.CAPITAL_ALLOCATED,
                    {
                        "from_sleeve_id": str(acct.unallocated.id),
                        "to_sleeve_id": str(sleeve.id),
                        "amount": str(plan.allocated),
                    },
                    sleeve_id=sleeve.id,
                    occurred_at=at + timedelta(minutes=3),
                    event_id=event_id_for(f"demo:alloc:{plan.key}"),
                )
            elif isinstance(payload, Dividend):
                await self._append(
                    acct,
                    LedgerEventType.DIVIDEND_RECEIVED,
                    {
                        "sleeve_id": str(sleeve.id),
                        "amount": str(payload.amount),
                        "symbol": payload.symbol,
                    },
                    sleeve_id=sleeve.id,
                    occurred_at=at,
                    event_id=event_id_for(f"demo:div:{plan.key}:{payload.symbol}:{at.date()}"),
                )
            elif isinstance(payload, Fill):
                await self._append_fill(acct, plan, sleeve, payload, lots, fill_counter)

        self.final_lots = lots

    async def _append_fill(
        self,
        acct: AccountState,
        plan: SessionPlan,
        sleeve: Sleeve,
        fill: Fill,
        lots: dict[tuple[str, str], list[FifoLot]],
        fill_counter: dict[str, int],
    ) -> None:
        key = (str(sleeve.id), fill.symbol)
        n = fill_counter.get(plan.key, 0) + 1
        fill_counter[plan.key] = n
        client_order_id = f"lt-demo-{plan.key}-{n:03d}"
        order_id = uuid4()
        notional = (fill.qty * fill.price).quantize(CENT)
        submitted = fill.at - timedelta(seconds=2)

        data: dict[str, str] = {
            "sleeve_id": str(sleeve.id),
            "symbol": fill.symbol,
            "side": fill.side,
            "qty": str(fill.qty),
            "price": str(fill.price),
            "fees": str(fill.fees),
            "client_order_id": client_order_id,
            "order_id": str(order_id),
        }

        if fill.side == "buy":
            # A buy reserves cash before it fills; the ORDER_FILLED releases it.
            await self._append(
                acct,
                LedgerEventType.ORDER_SUBMITTED,
                {
                    "sleeve_id": str(sleeve.id),
                    "client_order_id": client_order_id,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "reserved": str((notional + fill.fees).quantize(CENT)),
                    "order_id": str(order_id),
                },
                sleeve_id=sleeve.id,
                occurred_at=submitted,
                event_id=event_id_for(f"{client_order_id}:order_submitted"),
            )
            lots.setdefault(key, []).append(
                FifoLot(qty=fill.qty, cost_basis=notional, opened_seq=self._seq + 1)
            )
            self.pos_opened.setdefault(key, fill.at)
        else:
            result = select_lots_fifo(lots.get(key, []), fill.qty)
            lots[key] = result.remaining_lots
            cost = result.closed_cost_basis.quantize(CENT)
            realized = (notional - cost - fill.fees).quantize(CENT)
            data["cost_basis"] = str(cost)
            data["realized_pnl"] = str(realized)
            self.pos_realized[key] = self.pos_realized.get(key, ZERO) + realized

        await self._append(
            acct,
            LedgerEventType.ORDER_FILLED,
            data,
            sleeve_id=sleeve.id,
            occurred_at=fill.at,
            event_id=event_id_for(client_order_id),
        )
        self.order_rows.append(
            (
                plan,
                Order(
                    id=order_id,
                    tenant_id=self.tenant_id,
                    alpaca_order_id=f"demo-{client_order_id}",
                    client_order_id=client_order_id,
                    symbol=fill.symbol,
                    side=(
                        trading_pb2.ORDER_SIDE_BUY
                        if fill.side == "buy"
                        else trading_pb2.ORDER_SIDE_SELL
                    ),
                    order_type=trading_pb2.ORDER_TYPE_MARKET,
                    time_in_force=trading_pb2.TIME_IN_FORCE_DAY,
                    qty=fill.qty,
                    status=trading_pb2.ORDER_STATUS_FILLED,
                    filled_qty=fill.qty,
                    filled_avg_price=fill.price,
                    submitted_at=submitted,
                    filled_at=fill.at,
                    signal_reason=fill.reason,
                    metadata_={"source": "demo_seed", "mode": "live" if plan.live else "paper"},
                    sleeve_id=sleeve.id,
                    account_id=acct.account.id,
                    created_at=submitted,
                ),
            )
        )

    # trading rows

    async def seed_trading(self) -> None:
        self.plan_session: dict[str, TradingSession] = {}
        for plan in SESSION_PLANS:
            acct = self.accounts["live" if plan.live else "paper"]
            strat = self.strategy_rows[plan.strategy_id]
            current = latest_version(self.strategy_data[plan.strategy_id])
            session = TradingSession(
                id=uuid4(),
                tenant_id=self.tenant_id,
                strategy_id=strat.id,
                strategy_version=strat.current_version,
                credentials_id=acct.credentials_id,
                name=str(strat.name) if plan.live else f"{strat.name} (paper)",
                mode=common_pb2.EXECUTION_MODE_LIVE
                if plan.live
                else common_pb2.EXECUTION_MODE_PAPER,
                status=(
                    common_pb2.EXECUTION_STATUS_STOPPED
                    if plan.stop
                    else common_pb2.EXECUTION_STATUS_RUNNING
                ),
                config={"drift_tolerance": "0.05"},
                symbols=list(current["symbols"]),  # type: ignore[call-overload]
                started_at=et(plan.start, 10, 0),
                stopped_at=et(plan.stop, 15, 52) if plan.stop else None,
                last_heartbeat=et(plan.stop, 15, 52) if plan.stop else datetime.now(UTC),
                created_by=self.user_id,
                sleeve_id=self.plan_sleeve[plan.key].id,
                account_id=acct.account.id,
                created_at=et(plan.start, 9, 55),
            )
            self.db.add(session)
            await self.db.flush()
            self.plan_session[plan.key] = session
            self._bump("trading_sessions")

        for plan, order in self.order_rows:
            order.session_id = self.plan_session[plan.key].id
            self.db.add(order)
            self._bump("orders")
        await self.db.flush()
        await self.seed_positions()

    async def seed_positions(self) -> None:
        """Open positions per session (the ``positions`` table the Trading page
        reads), from the same FIFO lots that explain the fills, marked to the
        session day's close."""
        for plan in SESSION_PLANS:
            session = self.plan_session[plan.key]
            sleeve_key = str(self.plan_sleeve[plan.key].id)
            for (lot_sleeve, symbol), open_lots in self.final_lots.items():
                if lot_sleeve != sleeve_key:
                    continue
                qty = sum((lot.qty for lot in open_lots), ZERO)
                if qty <= ZERO:
                    continue
                cost_basis = sum((lot.cost_basis for lot in open_lots), ZERO).quantize(CENT)
                mark = price(symbol, SESSION_DAY)
                market_value = (qty * mark).quantize(CENT)
                unrealized = (market_value - cost_basis).quantize(CENT)
                opened_at = self.pos_opened.get((sleeve_key, symbol), session.started_at)
                self.db.add(
                    Position(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        session_id=session.id,
                        symbol=symbol,
                        side=trading_pb2.POSITION_SIDE_LONG,
                        qty=qty,
                        avg_entry_price=(cost_basis / qty).quantize(Decimal("0.00000001")),
                        current_price=mark,
                        market_value=market_value,
                        cost_basis=cost_basis,
                        unrealized_pl=unrealized,
                        unrealized_plpc=(unrealized / cost_basis).quantize(Decimal("0.000001"))
                        if cost_basis
                        else ZERO,
                        realized_pl=self.pos_realized.get((sleeve_key, symbol), ZERO),
                        is_open=True,
                        opened_at=opened_at,
                        created_at=opened_at,
                    )
                )
                self._bump("positions")
        await self.db.flush()

    # equity snapshots

    async def seed_snapshots(self) -> None:
        """Sleeve snapshots folded from each account's event stream and marked by
        the real ``compute_snapshot_values`` kernel: one at every trading day's
        close, then intraday marks on the session day (before the open's fills and
        after each one, the last at the live mark), so today's line moves with this
        morning's trades."""
        from src.ledger.projection import fold

        symbols = sorted(PATHS)
        for acct in self.accounts.values():
            if not acct.events:
                continue
            stamps: list[tuple[datetime, dict[str, Decimal]]] = []
            for d in trading_days(acct.events[0].occurred_at.astimezone(ET).date(), PREV_DAY):
                stamps.append((et(d, 16, 0), {s: price(s, d) for s in symbols}))
            if SESSION_DAY == TODAY:
                times = {et(SESSION_DAY, 9, 35)}
                times.update(
                    e.occurred_at + timedelta(seconds=1)
                    for e in acct.events
                    if e.occurred_at.astimezone(ET).date() == SESSION_DAY
                )
                ordered = sorted(times)
                for at in ordered[:-1]:
                    stamps.append((at, {s: intraday_price(s, at) for s in symbols}))
                # The latest mark is the live one the read side prices positions at.
                now = min(datetime.now(UTC), et(SESSION_DAY, 16, 0))
                closes = {s: price(s, SESSION_DAY) for s in symbols}
                stamps.append((max(ordered[-1], now), closes))
            else:
                stamps.append((et(SESSION_DAY, 16, 0), {s: price(s, SESSION_DAY) for s in symbols}))

            # The latest stamp per (sequence, UTC day) wins, the snapshot table's unique key.
            keyed: dict[tuple[int, date], tuple[datetime, dict[str, Decimal], list[SeedEvent]]] = {}
            for at, prices in stamps:
                events_upto = [e for e in acct.events if e.occurred_at <= at]
                if events_upto:
                    keyed[(events_upto[-1].sequence, at.date())] = (at, prices, events_upto)
            for (seq, _), (at, prices, events_upto) in keyed.items():
                projection = fold(events_upto)  # type: ignore[arg-type]
                values: list[SnapshotValue] = compute_snapshot_values(projection, prices, seq)
                for v in values:
                    self.db.add(
                        SleeveSnapshot(
                            id=uuid4(),
                            tenant_id=self.tenant_id,
                            sleeve_id=UUID(v.sleeve_id),
                            as_of_sequence=v.as_of_sequence,
                            cash_balance=v.cash_balance,
                            reserved_cash=v.reserved_cash,
                            equity=v.equity,
                            lots=v.lots,
                            created_at=at,
                        )
                    )
                    self._bump("ledger_sleeve_snapshots")
            await self.db.flush()

    # market-data bars

    async def seed_market_bars(self) -> None:
        """Daily OHLCV bars in the market-data store, from the same price paths as
        the fills and snapshots. With no Alpaca feed in the demo, the newest bar's
        close is the live mark. The window is cleared first so a bar left on a
        holiday by an older seed can't put a spike in the curve."""
        symbols = sorted(PATHS)
        rows: list[dict[str, object]] = []
        fetched = datetime.now(UTC)
        for symbol in symbols:
            series = PRICES[symbol]
            for i, d in enumerate(MARKET_DAYS):
                close = series[i]
                open_ = series[i - 1] if i else close
                wiggle = Decimal(str(1 + stable_rng(f"hl:{symbol}:{d}").uniform(0.001, 0.006)))
                high = (max(open_, close) * wiggle).quantize(CENT)
                low = (min(open_, close) / wiggle).quantize(CENT)
                vol = 800_000 + (d.toordinal() * 7919 + sum(ord(c) for c in symbol)) % 5_000_000
                rows.append(
                    {
                        "time": dt(d, 5, 0),
                        "symbol": symbol,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": vol,
                        "vwap": ((high + low + close) / 3).quantize(CENT),
                        "trade_count": vol // 100,
                        "adjustment": "raw",
                        "fetched_at": fetched,
                    }
                )

        engine = create_async_engine(MARKET_DATA_DB_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    BARS_DAILY.delete()
                    .where(BARS_DAILY.c.symbol.in_(symbols))
                    .where(BARS_DAILY.c.time >= dt(BARS_START, 0, 0))
                )
                for i in range(0, len(rows), 1000):
                    await conn.execute(pg_insert(BARS_DAILY).values(rows[i : i + 1000]))
        finally:
            await engine.dispose()
        self._bump("market_data_bars", len(rows))

    # backtests

    async def seed_backtests(self) -> None:
        """Completed backtests run over the same price paths as the sessions, so a
        session and its backtest over the same dates move together. Metrics are
        derived from each curve the way the engine derives them (metrics.py)."""
        for sid, runs in BACKTEST_RUNS.items():
            strat = self.strategy_rows[sid]
            versions: list[dict[str, object]] = self.strategy_data[sid]["versions"]  # type: ignore[assignment]
            win_rate, profit_factor, trades = TRADE_STATS[sid]
            for run in runs:
                version = versions[run.version - 1]
                symbols = list(version["symbols"])  # type: ignore[call-overload]
                rule = rule_for(sid, run.version)
                daily = backtest_curve(
                    rule, str(version["rebalance"]), BT_START, run.end, BT_INITIAL
                )
                spy = [(d, float(price("SPY", d))) for d, _ in daily]
                await self._add_backtest(
                    strat,
                    run,
                    symbols,
                    daily,
                    spy,
                    BacktestSpec(sid, win_rate, profit_factor, trades),
                )

    async def _add_backtest(
        self,
        strat: Strategy,
        run: RunSpec,
        symbols: list[str],
        daily: list[tuple[date, float]],
        spy: list[tuple[date, float]],
        spec: BacktestSpec,
    ) -> None:
        initial = BT_INITIAL
        curve_points = [(dt(d, 21, 0), eq) for d, eq in daily]
        equity = [eq for _, eq in daily]
        total_return, annual_return, daily_returns = bt_returns(equity, initial, len(equity))
        daily_arr = np.array(daily_returns)
        eq_arr = np.array(equity, dtype=float)
        max_dd_pos, dd_duration = bt_max_drawdown(eq_arr)
        final_equity = float(eq_arr[-1])
        st = self._synth_trades(spec, symbols, final_equity - initial, daily[0][0], daily[-1][0])

        spy_bars = [(dt(d, 21, 0), close) for d, close in spy]
        shares = initial / spy[0][1]
        benchmark_curve: list[dict[str, object]] = [
            {"date": ts.isoformat(), "equity": round(shares * close, 2)} for ts, close in spy_bars
        ]
        benchmark_return = spy[-1][1] / spy[0][1] - 1.0
        strat_ret, bench_ret = bt_align_daily_returns(curve_points, spy_bars)
        alpha, beta = bt_alpha_beta(strat_ret, bench_ret)
        info_ratio = bt_information_ratio(strat_ret, bench_ret)
        started = run.completed - timedelta(minutes=4)

        bt = Backtest(
            id=uuid4(),
            tenant_id=self.tenant_id,
            strategy_id=strat.id,
            strategy_version=run.version,
            name=f"{strat.name} v{run.version}, {daily[0][0]:%b %Y} to {daily[-1][0]:%b %Y}",
            status=backtest_pb2.BACKTEST_STATUS_COMPLETED,
            config={
                "commission": 0.0,
                "slippage": 0.0,
                "timeframe": "1D",
                "benchmark_symbol": "SPY",
                "include_benchmark": True,
            },
            symbols=symbols,
            start_date=daily[0][0],
            end_date=daily[-1][0],
            initial_capital=Decimal(str(initial)),
            started_at=started,
            completed_at=run.completed,
            created_by=self.user_id,
            created_at=started,
        )
        self.db.add(bt)
        await self.db.flush()
        self._bump("backtests")

        self.db.add(
            BacktestResult(
                id=uuid4(),
                backtest_id=bt.id,
                total_return=Decimal(str(round(total_return, 6))),
                annual_return=Decimal(str(round(annual_return, 6))),
                sharpe_ratio=Decimal(str(round(bt_sharpe(daily_arr), 4))),
                sortino_ratio=Decimal(str(round(bt_sortino(daily_arr), 4))),
                # Stored negative; the UI renders the negative-fraction convention.
                max_drawdown=Decimal(str(round(-max_dd_pos, 6))),
                max_drawdown_duration=dd_duration,
                win_rate=Decimal(str(round(st.win_rate, 4))),
                profit_factor=Decimal(str(round(st.profit_factor, 4)))
                if st.profit_factor is not None
                else None,
                exposure_time=Decimal(
                    str(round(stable_rng(f"{spec.strategy_id}:exposure").uniform(92.0, 99.9), 2))
                ),
                total_trades=st.total,
                winning_trades=st.winning,
                losing_trades=st.losing,
                avg_trade_return=Decimal(str(round(st.avg_trade_return, 6))),
                final_equity=Decimal(str(round(final_equity, 2))),
                equity_curve=[
                    {"date": ts.isoformat(), "equity": round(eq, 2)} for ts, eq in curve_points
                ],
                trades=st.trades,
                daily_returns=[round(r, 8) for r in daily_returns],
                monthly_returns={
                    k: round(v, 6) for k, v in bt_monthly_returns(curve_points, initial).items()
                },
                benchmark_return=Decimal(str(round(benchmark_return, 6))),
                benchmark_symbol="SPY",
                alpha=Decimal(str(round(alpha, 6))) if alpha is not None else None,
                beta=Decimal(str(round(beta, 4))) if beta is not None else None,
                information_ratio=Decimal(str(round(info_ratio, 4)))
                if info_ratio is not None
                else None,
                benchmark_equity_curve=benchmark_curve,
            )
        )
        self._bump("backtest_results")

    def _synth_trades(
        self, spec: BacktestSpec, symbols: list[str], target_pnl: float, start: date, end: date
    ) -> SynthTrades:
        """The FULL trade list (len == spec.trades) whose P&Ls SUM EXACTLY to
        ``target_pnl`` — the curve's final-equity gain — so the equity curve, the
        headline counts, and the paged trade log all reconcile. Realistic entries
        are drawn first, then winners and losers are scaled independently to hit
        the gross-profit / gross-loss split implied by ``spec.win_rate`` and
        ``spec.profit_factor`` (engine convention: win = pnl > 0). total / winning
        / losing / win_rate / profit_factor / avg_trade_return are all derived FROM
        the resulting list, so nothing can disagree with the stored trades."""
        rng = stable_rng(spec.strategy_id + ":trades")
        total = spec.trades
        n_win = max(1, min(total - 1, round(spec.win_rate * total)))
        flags = [True] * n_win + [False] * (total - n_win)
        rng.shuffle(flags)  # interleave winners/losers across the window

        span = (end - start).days
        raw: list[_RawTrade] = []
        for i, is_win in enumerate(flags):
            entry = round(rng.uniform(40, 320), 2)
            qty = rng.randint(5, 60)
            pct = rng.uniform(0.005, 0.09) if is_win else -rng.uniform(0.005, 0.07)
            entry_day = start + timedelta(days=rng.randint(0, max(1, span - 10)))
            exit_day = min(entry_day + timedelta(days=rng.randint(3, 40)), end)
            raw.append(
                _RawTrade(
                    symbol=symbols[i % len(symbols)],
                    entry=entry,
                    qty=qty,
                    win=is_win,
                    natural=round(entry * pct * qty, 2),
                    entry_day=entry_day,
                    exit_day=exit_day,
                )
            )

        # Split the target into gross win (positive) and gross loss (magnitude) so
        # gross_win - gross_loss == target and gross_win / gross_loss == profit_factor
        # (both positive for the seeded specs — all CAGR > 0, PF > 1), then scale
        # winners and losers onto those totals.
        nat_win = sum(t.natural for t in raw if t.win)
        nat_loss = -sum(t.natural for t in raw if not t.win)
        pf = spec.profit_factor
        if target_pnl >= 0 and pf > 1.0:
            gross_loss = target_pnl / (pf - 1.0)
            gross_win = target_pnl + gross_loss
        else:  # degenerate target (unused): keep the sum, drop the PF guarantee
            gross_win = max(target_pnl, 0.0)
            gross_loss = gross_win - target_pnl
        scale_win = gross_win / nat_win if nat_win > 0 else 0.0
        scale_loss = gross_loss / nat_loss if nat_loss > 0 else 0.0

        pnls = [round(t.natural * (scale_win if t.win else scale_loss), 2) for t in raw]
        # Cents residual → largest-magnitude trade so Σ(pnl) == target exactly.
        if pnls:
            residual = round(target_pnl - sum(pnls), 2)
            k = max(range(len(pnls)), key=lambda i: abs(pnls[i]))
            pnls[k] = round(pnls[k] + residual, 2)

        trades: list[dict[str, object]] = []
        pnl_pcts: list[float] = []
        for t, pnl in zip(raw, pnls, strict=True):
            exit_px = round(t.entry + pnl / t.qty, 2) if t.qty else t.entry
            pnl_pct = round(pnl / (t.entry * t.qty), 6) if t.entry * t.qty else 0.0
            pnl_pcts.append(pnl_pct)
            trades.append(
                {
                    # Keys mirror what a real backtest persists (see _persist).
                    "symbol": t.symbol,
                    "side": "long",
                    "entry_date": dt(t.entry_day, 21, 0).isoformat(),
                    "exit_date": dt(t.exit_day, 21, 0).isoformat(),
                    "entry_price": t.entry,
                    "exit_price": exit_px,
                    "quantity": t.qty,
                    "pnl": pnl,
                    "pnl_percent": pnl_pct,
                    "commission": 0.0,
                }
            )

        n = len(trades)
        winning = sum(1 for p in pnls if p > 0)  # engine: pnl > 0
        gross_win_actual = sum(p for p in pnls if p > 0)
        gross_loss_actual = abs(sum(p for p in pnls if p <= 0))
        return SynthTrades(
            trades=trades,
            total=n,
            winning=winning,
            losing=n - winning,  # engine: pnl <= 0
            win_rate=winning / n if n else 0.0,
            profit_factor=gross_win_actual / gross_loss_actual if gross_loss_actual > 0 else None,
            avg_trade_return=sum(pnl_pcts) / n if n else 0.0,
        )

    # agent

    async def seed_agent(self) -> None:
        # The real "build a strategy" flow calls the genuine ``validate_dsl`` tool
        # and, on success, persists a PENDING strategy artifact as a side effect.
        mom = self.strategy_data["momentum-sectors"]
        mom_current = latest_version(mom)
        mom_dsl = str(mom_current["config_sexpr"])
        mom_symbols = list(mom_current["symbols"])  # type: ignore[call-overload]
        mom_description = str(mom["description"])
        momentum_validate_call = [
            {
                "id": "toolu_demo_momentum_validate",
                "name": "validate_dsl",
                "arguments": {"dsl_code": mom_dsl},
                "result": {
                    "valid": True,
                    "errors": [],
                    "strategy_name": "Momentum Sectors",
                    "rebalance_frequency": "weekly",
                    "benchmark": "SPY",
                    "symbols": mom_symbols,
                    "indicators": ["momentum"],
                },
                "duration_ms": 38,
                "success": True,
            }
        ]
        sessions: list[dict[str, object]] = [
            {
                "title": "Build a momentum sector strategy",
                "status": agent_pb2.AGENT_SESSION_STATUS_COMPLETED,
                "day": days_ago(28),
                "messages": [
                    (
                        "user",
                        "I want a strategy that rotates into the strongest market sectors. Can you help me build one?",
                        None,
                    ),
                    (
                        "assistant",
                        "Sure. A sector-momentum rotation ranks the 11 S&P sector ETFs by their trailing return and holds the leaders in equal weights. Your current Momentum Sectors holds the top 3 by 90-day momentum and rebalances weekly. Want me to add real estate (XLRE) so all 11 sectors compete?",
                        None,
                    ),
                    ("user", "Yes, add XLRE and keep everything else the same.", None),
                    (
                        "assistant",
                        "Done. I've updated **Momentum Sectors** and validated it: the top 3 of 11 sector ETFs by 90-day momentum, equal weight, rebalanced weekly. Momentum's drawdowns run deeper than a broad index fund's, so expect bumpier weeks. Review it below, then save it as a new version.",
                        momentum_validate_call,
                    ),
                ],
                "summary": (
                    "Added XLRE to Momentum Sectors so all 11 sector ETFs compete; top 3 by 90-day momentum, weekly.",
                    "User wanted the sector rotation to cover every sector. Added XLRE to the universe and kept the top-3, 90-day, weekly rules; discussed momentum's deeper drawdowns.",
                    ["momentum", "sector rotation"],
                    ["Momentum Sectors"],
                    ["Hold the top 3 of 11 sectors", "Rebalance weekly"],
                ),
            },
            {
                "title": "Should I keep Tech Momentum Rotation running?",
                "status": agent_pb2.AGENT_SESSION_STATUS_COMPLETED,
                "day": TM_STOP,
                "messages": [
                    (
                        "user",
                        "Tech Momentum Rotation is down about 2% since it started in paper. Should I keep it running?",
                        None,
                    ),
                    (
                        "assistant",
                        "Most of the loss came from the last three weeks. Semiconductors led into October, so the session moved into SMH and XLK, and both fell harder than QQQ once the rally turned. A weekly rotation across three funds this closely related tends to switch late and pay for each reversal. Its backtest still shows a strong two-year return, but with a drawdown above 20%.",
                        None,
                    ),
                    ("user", "Stop it and keep the cash in the sleeve for now.", None),
                    (
                        "assistant",
                        "Stopped. The positions were sold at the 15:50 rebalance and the sleeve now holds cash. You can restart it in paper from the Strategies page whenever you like.",
                        None,
                    ),
                ],
                "summary": (
                    "Explained Tech Momentum Rotation's paper loss (late rotation into SMH and XLK before a pullback); user stopped the session and kept the cash in its sleeve.",
                    "User asked whether to keep Tech Momentum Rotation running after a small paper loss. Attributed it to late weekly rotation among highly correlated tech funds. User chose to stop the session and hold cash.",
                    ["momentum", "drawdown", "semiconductors"],
                    ["Tech Momentum Rotation"],
                    ["Stop Tech Momentum Rotation", "Keep the sleeve in cash"],
                ),
            },
            {
                "title": "What is dual momentum?",
                "status": agent_pb2.AGENT_SESSION_STATUS_COMPLETED,
                "day": days_ago(13),
                "messages": [
                    (
                        "user",
                        "What's the difference between dual momentum and my Momentum Sectors strategy?",
                        None,
                    ),
                    (
                        "assistant",
                        "Dual momentum combines **relative** momentum (hold the stronger of a few assets) with **absolute** momentum (only hold it while it is beating cash). When nothing has positive momentum it moves to bonds, a built-in defensive switch. Momentum Sectors uses relative momentum only, so it stays invested in a downturn. The Dual Momentum template compares SPY with EFA and falls back to BND.",
                        None,
                    ),
                ],
                "summary": None,
            },
            {
                "title": "Buy SPY after a sharp drop",
                "status": agent_pb2.AGENT_SESSION_STATUS_ACTIVE,
                "day": days_ago(2),
                "messages": [
                    ("user", "Can you draft a strategy that buys SPY after a sharp drop?", None),
                    (
                        "assistant",
                        "Here's a simple version: hold SPY when its 5-day RSI falls under 25, and park in BIL otherwise, checked each trading day. I've saved it as a draft called **Pullback Buyer**. It hasn't been backtested yet, so run a backtest before you start it in paper.",
                        None,
                    ),
                ],
                "summary": None,
            },
        ]

        momentum_session_id: UUID | None = None
        for s in sessions:
            msgs: list[tuple[str, str, object]] = s["messages"]  # type: ignore[assignment]
            day: date = s["day"]  # type: ignore[assignment]
            session = AgentSession(
                id=uuid4(),
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                title=str(s["title"]),
                status=s["status"],  # type: ignore[arg-type]
                message_count=len(msgs),
                last_activity_at=et(day, 16, 0),
                created_at=et(day, 15, 30),
            )
            self.db.add(session)
            await self.db.flush()
            self._bump("agent_sessions")
            if s["title"] == "Build a momentum sector strategy":
                momentum_session_id = session.id

            for i, (role, content, tool_calls) in enumerate(msgs):
                self.db.add(
                    AgentMessage(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        session_id=session.id,
                        role=agent_pb2.MESSAGE_ROLE_USER
                        if role == "user"
                        else agent_pb2.MESSAGE_ROLE_ASSISTANT,
                        content=content,
                        tool_calls_json=tool_calls,
                        created_at=et(day, 15, 30) + timedelta(minutes=i),
                    )
                )
                self._bump("agent_messages")

        # Backing pending artifact for the Momentum Sectors turn, left uncommitted
        # so GetSession surfaces it.
        if momentum_session_id is not None:
            self.db.add(
                PendingArtifact(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    session_id=momentum_session_id,
                    artifact_type=agent_pb2.ARTIFACT_TYPE_STRATEGY,
                    name="Momentum Sectors",
                    description=mom_description,
                    artifact_json={
                        "name": "Momentum Sectors",
                        "description": mom_description,
                        "dsl_code": mom_dsl,
                        "symbols": mom_symbols,
                    },
                    is_committed=False,
                    created_at=et(days_ago(28), 15, 33),
                )
            )
            self._bump("pending_artifacts")

        facts = [
            (
                "risk_tolerance",
                "Moderate risk tolerance; comfortable with drawdowns up to about 15%.",
                0.9,
            ),
            (
                "asset_preference",
                "Prefers broad, liquid ETFs; likes a tech tilt but wants diversification.",
                0.85,
            ),
            (
                "investment_goal",
                "Long-term growth, about a 15 year horizon toward retirement.",
                0.8,
            ),
            (
                "strategy_decision",
                "Runs All-Weather Portfolio live as the core; Recession Radar and Momentum Sectors stay in paper until they prove out.",
                0.88,
            ),
            (
                "trading_behavior",
                "Tests every strategy in paper before going live and stops sessions that lag their backtest.",
                0.75,
            ),
        ]
        for category, content, confidence in facts:
            self.db.add(
                AgentMemoryFact(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    category=category,
                    content=content,
                    confidence=confidence,
                    extraction_method="llm",
                    is_active=True,
                    last_accessed_at=et(days_ago(2), 10, 0),
                    access_count=RNG.randint(1, 6),
                    created_at=et(days_ago(160), 10, 0),
                )
            )
            self._bump("agent_memory_facts")

    # run

    async def run(self) -> None:
        plan_sessions(load_strategy_data())
        await self.purge_existing()
        await self.seed_identity()
        await self.seed_billing()
        await self.seed_strategies()
        await self.seed_ledger_identity()
        await self.seed_ledger_events()
        await self.seed_trading()
        await self.seed_snapshots()
        await self.seed_market_bars()
        await self.seed_backtests()
        await self.seed_agent()


def dry_run() -> None:
    plan_sessions(load_strategy_data())
    for plan in SESSION_PLANS:
        held: dict[str, Decimal] = {}
        cash = plan.allocated + sum((d.amount for d in plan.dividends), ZERO)
        for f in plan.fills:
            sign = 1 if f.side == "buy" else -1
            held[f.symbol] = held.get(f.symbol, ZERO) + sign * f.qty
            cash -= sign * f.qty * f.price
        value = cash + sum((q * price(s, SESSION_DAY) for s, q in held.items()), ZERO)
        prev = cash + sum((q * price(s, PREV_DAY) for s, q in held.items()), ZERO)
        days = {f.at.astimezone(ET).date() for f in plan.fills}
        logger.info(
            "%s value=%.2f return=%.2f%% today=%.2f fills=%d days=%d cash=%.2f holds=%s",
            plan.key,
            value,
            float(value / plan.allocated - 1) * 100,
            value - prev,
            len(plan.fills),
            len(days),
            cash,
            {s: str(q) for s, q in held.items() if q},
        )
    for sid, runs in BACKTEST_RUNS.items():
        versions: list[dict[str, object]] = load_strategy_data()[sid]["versions"]  # type: ignore[assignment]
        for run in runs:
            daily = backtest_curve(
                rule_for(sid, run.version),
                str(versions[run.version - 1]["rebalance"]),
                BT_START,
                run.end,
                BT_INITIAL,
            )
            eq = np.array([e for _, e in daily])
            dd, _ = bt_max_drawdown(eq)
            logger.info(
                "bt %s v%d %s..%s return=%.1f%% maxdd=%.1f%%",
                sid,
                run.version,
                daily[0][0],
                daily[-1][0],
                (eq[-1] / BT_INITIAL - 1) * 100,
                -dd * 100,
            )
    spy = float(price("SPY", PREV_DAY) / price("SPY", BT_START)) - 1
    logger.info("SPY %s..%s %.1f%%", BT_START, PREV_DAY, spy * 100)


async def main() -> None:
    if os.getenv("DEMO_SEED_DRY_RUN"):
        dry_run()
        return
    session_maker = get_session_maker()
    async with session_maker() as db:
        seeder = Seeder(db)
        try:
            await seeder.run()
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("seed failed; rolled back")
            raise

    logger.info("=" * 60)
    logger.info("DEMO SEED COMPLETE (session day %s)", SESSION_DAY)
    logger.info("  login: %s / %s", DEMO_EMAIL, DEMO_PASSWORD)
    logger.info("  tenant: %s (%s)", TENANT_NAME, DEMO_SLUG)
    for key in sorted(seeder.counts):
        logger.info("  %-26s %d", key, seeder.counts[key])
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
