"""Seed a polished, internally-consistent demo tenant for LlamaTrade.

Login: ``demo@llamatrade.ai`` / ``demo1234``.

Creates one "lived-in" retail-trader account across every product surface:
auth, billing, strategies, backtests, the portfolio double-entry ledger
(account / sleeves / events / equity-curve snapshots), trading
(sessions / orders / positions), and the AI copilot (sessions / messages /
memory).

Design + invariants: ``.docs/planning/demo-seed-blueprint.md``.

Runs INSIDE the ``portfolio`` container so it can reuse the real ledger kernel
(``src.ledger.*`` + ``src.tasks.equity_snapshot``) rather than hand-writing
balances — every economic event is appended through ``LedgerWriter`` (which
asserts double-entry conservation), sells resolve cost basis through the real
FIFO selector, and the equity curve is produced by the real snapshot computer.

Idempotent: it transactionally deletes the demo tenant (found by fixed slug) and
everything scoped to it, then recreates. It never touches another tenant. Global
``plans`` are get-or-created, never deleted.

    docker cp scripts/demo_seed_data llamatrade-portfolio:/app/demo_seed_data
    docker cp scripts/seed_demo_account.py llamatrade-portfolio:/app/seed_demo_account.py
    docker exec -w /app llamatrade-portfolio python seed_demo_account.py
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
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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

# Real ledger kernel — reused, never re-implemented.
from llamatrade_common.utils import encrypt_value
from llamatrade_db import get_session_maker
from llamatrade_db.models import (
    Account,
    AgentMemoryFact,
    AgentMessage,
    AgentSession,
    AgentSessionSummary,
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
DEMO_AVATAR_URL = "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=160&h=160&fit=crop&crop=face"

# Pre-generated valid bcrypt hash of "demo1234" (self-verifying via checkpw).
# Fallback for containers without the `bcrypt` module (e.g. portfolio).
_DEMO_PASSWORD_HASH_FALLBACK = "$2b$12$nY6hP1l0Ig4tHIKkdvYX.uHlErnFjher2YvzZaxftVECaQb3DlNXW"

# Freshness: TODAY tracks the wall clock so the demo is always current, but is
# floored at the original anchor so it never regresses behind the fixed 2026
# fills/invoices/backtest window (which would put seeded events in the future).
# Everything else stays deterministic (fixed RNG seeds, fixed price path shape).
TODAY = max(date.today(), date(2026, 7, 13))
DEPOSIT_DAY = date(2026, 1, 6)
INITIAL_DEPOSIT = Decimal("100000.00")

# Market-data (Timescale) daily bars are seeded so open positions mark to market
# and the equity-vs-SPY overlays have a benchmark series. The store is a separate
# database from the main app DB; the URL falls back to the compose default.
MARKET_DATA_DB_URL = os.getenv(
    "MARKET_DATA_DB_URL",
    "postgresql+asyncpg://postgres:postgres@timescaledb:5432/market_data",
)
BARS_START = date(2026, 1, 2)  # a few sessions before the deposit, for benchmark runway

DATA_DIR = Path(__file__).resolve().parent / "demo_seed_data"
# When copied into the container next to the script, the data dir sits at /app/demo_seed_data.
if not DATA_DIR.exists():
    DATA_DIR = Path("/app/demo_seed_data")

ZERO = Decimal("0")
CENT = Decimal("0.01")
RNG = random.Random(20260713)

# Deterministic per-symbol price path: (start, end) over [DEPOSIT_DAY, TODAY].
PRICE_PATH: dict[str, tuple[Decimal, Decimal]] = {
    "VTI": (Decimal("275"), Decimal("292")),
    "TLT": (Decimal("92"), Decimal("89")),
    "IEF": (Decimal("95"), Decimal("96")),
    "GLD": (Decimal("205"), Decimal("224")),
    "DBC": (Decimal("22.5"), Decimal("24")),
    "SPY": (Decimal("500"), Decimal("535")),
    "LQD": (Decimal("108"), Decimal("109.5")),
    "VNQ": (Decimal("88"), Decimal("91")),
    "XLK": (Decimal("235"), Decimal("262")),
    "XLF": (Decimal("46"), Decimal("49")),
    "XLV": (Decimal("150"), Decimal("149")),
    "XLE": (Decimal("92"), Decimal("87")),
    "AAPL": (Decimal("230"), Decimal("246")),
    # Extended universe so every seeded strategy's symbols have real bars (no
    # market-data gaps → backtests run entirely off the store, no Alpaca fetch).
    "BIL": (Decimal("91.4"), Decimal("91.5")),
    "BND": (Decimal("72"), Decimal("72.6")),
    "BNDX": (Decimal("48.5"), Decimal("48.9")),
    "DBMF": (Decimal("27"), Decimal("28.2")),
    "EDV": (Decimal("74"), Decimal("70.5")),
    "IWM": (Decimal("218"), Decimal("231")),
    "MINT": (Decimal("101.8"), Decimal("102")),
    "PDBC": (Decimal("13.8"), Decimal("14.5")),
    "QQQ": (Decimal("440"), Decimal("471")),
    "SGOV": (Decimal("100.4"), Decimal("100.6")),
    "SHY": (Decimal("82"), Decimal("82.4")),
    "TIP": (Decimal("108"), Decimal("109.5")),
    "UNG": (Decimal("15.5"), Decimal("13.2")),
    "USFR": (Decimal("50.4"), Decimal("50.6")),
    "USO": (Decimal("80"), Decimal("75.5")),
    "VEA": (Decimal("49.5"), Decimal("52.8")),
    "VGIT": (Decimal("58.5"), Decimal("59.4")),
    "VNQI": (Decimal("44.5"), Decimal("46.2")),
    "VWO": (Decimal("43.5"), Decimal("46")),
    "XLB": (Decimal("89"), Decimal("92.5")),
    "XLC": (Decimal("98"), Decimal("106")),
    "XLI": (Decimal("134"), Decimal("142")),
    "XLP": (Decimal("81.5"), Decimal("83.8")),
    "XLRE": (Decimal("41.5"), Decimal("42.8")),
    "XLU": (Decimal("77.5"), Decimal("82")),
    "XLY": (Decimal("204"), Decimal("216")),
}

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


def password_hash() -> str:
    """bcrypt hash of DEMO_PASSWORD; fresh if bcrypt is present, else the constant."""
    try:
        import bcrypt

        return bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    except ModuleNotFoundError:
        logger.info("bcrypt not installed here; using pre-generated demo1234 hash")
        return _DEMO_PASSWORD_HASH_FALLBACK


def dt(d: date, hour: int = 15, minute: int = 30) -> datetime:
    """UTC datetime at a given wall time on a date."""
    return datetime.combine(d, time(hour, minute), tzinfo=UTC)


def dt_naive(d: date, hour: int = 15, minute: int = 30) -> datetime:
    """Naive datetime — for the few columns declared without ``timezone=True``
    (``strategy_executions.started_at`` / ``stopped_at``)."""
    return datetime.combine(d, time(hour, minute))


def price_at(symbol: str, d: date) -> Decimal:
    """Interpolate the symbol's price on date ``d`` with a small deterministic wiggle."""
    start, end = PRICE_PATH[symbol]
    span = (TODAY - DEPOSIT_DAY).days or 1
    frac = max(0.0, min(1.0, (d - DEPOSIT_DAY).days / span))
    base = start + (end - start) * Decimal(str(frac))
    # Deterministic per-symbol phase (PYTHONHASHSEED is unset, so ``hash`` would
    # vary run-to-run and desync snapshots from the seeded market-data bars).
    phase = sum(ord(c) for c in symbol) % 7
    days = (d - DEPOSIT_DAY).days
    # Slow swing shapes the multi-week curve; a faster, per-symbol-decorrelated
    # term adds realistic day-to-day volatility so a single-session P&L isn't ~0.
    wiggle = math.sin(days / 11.0 + phase) * 0.012 + math.sin(days * 1.1 + phase * 1.7) * 0.005
    return (base * (Decimal("1") + Decimal(str(wiggle)))).quantize(CENT)


# Trade plan (drives ledger fills, orders, positions)


@dataclass(frozen=True)
class Fill:
    day: date
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    price: Decimal
    fees: Decimal = ZERO


@dataclass
class SleevePlan:
    key: str  # short id used to build client_order_ids
    name: str
    kind: SleeveType
    strategy_id: str  # template id (or "manual")
    allocated: Decimal
    alloc_day: date
    fills: list[Fill]
    color: str = "#6366f1"
    live: bool = False


SLEEVE_PLANS: list[SleevePlan] = [
    SleevePlan(
        key="allw",
        name="All-Weather Portfolio",
        kind=SleeveType.STRATEGY,
        strategy_id="all-weather",
        allocated=Decimal("35000.00"),
        alloc_day=date(2026, 1, 15),
        color="#0ea5e9",
        live=True,
        fills=[
            Fill(date(2026, 1, 16), "VTI", "buy", Decimal("30"), Decimal("275.00")),
            Fill(date(2026, 1, 16), "TLT", "buy", Decimal("90"), Decimal("92.00")),
            Fill(date(2026, 1, 16), "IEF", "buy", Decimal("80"), Decimal("95.00")),
            Fill(date(2026, 1, 16), "GLD", "buy", Decimal("30"), Decimal("205.00")),
            Fill(date(2026, 1, 16), "DBC", "buy", Decimal("200"), Decimal("22.50")),
            # Quarterly rebalance: trim long bonds, top up equities.
            Fill(date(2026, 4, 15), "TLT", "sell", Decimal("20"), Decimal("89.50")),
            Fill(date(2026, 4, 15), "VTI", "buy", Decimal("6"), Decimal("286.00")),
        ],
    ),
    SleevePlan(
        key="rp",
        name="Risk Parity",
        kind=SleeveType.STRATEGY,
        strategy_id="risk-parity",
        allocated=Decimal("30000.00"),
        alloc_day=date(2026, 1, 15),
        color="#10b981",
        live=True,
        fills=[
            Fill(date(2026, 1, 17), "SPY", "buy", Decimal("15"), Decimal("500.00")),
            Fill(date(2026, 1, 17), "TLT", "buy", Decimal("70"), Decimal("92.50")),
            Fill(date(2026, 1, 17), "GLD", "buy", Decimal("30"), Decimal("205.00")),
            Fill(date(2026, 1, 17), "LQD", "buy", Decimal("55"), Decimal("108.00")),
            Fill(date(2026, 1, 17), "VNQ", "buy", Decimal("40"), Decimal("88.00")),
        ],
    ),
    SleevePlan(
        key="mom",
        name="Momentum Sectors",
        kind=SleeveType.STRATEGY,
        strategy_id="momentum-sectors",
        allocated=Decimal("20000.00"),
        alloc_day=date(2026, 1, 20),
        color="#f59e0b",
        live=True,
        fills=[
            Fill(date(2026, 1, 22), "XLK", "buy", Decimal("30"), Decimal("235.00")),
            Fill(date(2026, 1, 22), "XLF", "buy", Decimal("60"), Decimal("46.00")),
            Fill(date(2026, 1, 22), "XLV", "buy", Decimal("40"), Decimal("150.00")),
            Fill(date(2026, 1, 22), "XLE", "buy", Decimal("40"), Decimal("92.00")),
            # Monthly momentum rotation: energy weakened, rotate into tech.
            Fill(date(2026, 5, 11), "XLE", "sell", Decimal("40"), Decimal("87.50")),
            Fill(date(2026, 5, 11), "XLK", "buy", Decimal("12"), Decimal("250.00")),
        ],
    ),
    SleevePlan(
        key="man",
        name="Manual",
        kind=SleeveType.MANUAL,
        strategy_id="manual",
        allocated=Decimal("5000.00"),
        alloc_day=date(2026, 2, 1),
        color="#94a3b8",
        live=False,
        fills=[
            Fill(date(2026, 2, 5), "AAPL", "buy", Decimal("20"), Decimal("230.00")),
            Fill(date(2026, 6, 20), "AAPL", "sell", Decimal("20"), Decimal("245.50")),
        ],
    ),
]

# Dividends credited to a sleeve (nice flavor; balanced cash↔pnl legs).
DIVIDENDS: list[tuple[str, date, str, Decimal]] = [
    ("rp", date(2026, 3, 20), "LQD", Decimal("48.00")),
]

# In-memory ledger event mirror (for folding the equity curve)


@dataclass
class SeedEvent:
    """Duck-types ``LedgerEventLike`` for the pure ``fold`` kernel."""

    event_type: str
    data: dict[str, str]
    sequence: int
    occurred_at: datetime
    event_id: str = ""


# Backtest specs (varied, not all winners)


@dataclass(frozen=True)
class BacktestSpec:
    strategy_id: str
    ann_return: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_dd: float  # negative
    win_rate: float
    profit_factor: float
    trades: int


BACKTEST_SPECS: dict[str, BacktestSpec] = {
    "classic-60-40": BacktestSpec(
        "classic-60-40", 0.072, 0.084, 0.85, 1.18, -0.125, 0.55, 1.42, 96
    ),
    "all-weather": BacktestSpec("all-weather", 0.068, 0.061, 1.05, 1.55, -0.089, 0.58, 1.66, 88),
    "risk-parity": BacktestSpec("risk-parity", 0.084, 0.067, 1.25, 1.83, -0.102, 0.60, 1.91, 120),
    "momentum-sectors": BacktestSpec(
        "momentum-sectors", 0.115, 0.168, 0.72, 0.98, -0.198, 0.48, 1.28, 156
    ),
    "vigilant-asset-allocation": BacktestSpec(
        "vigilant-asset-allocation", 0.128, 0.082, 1.55, 2.10, -0.095, 0.62, 2.15, 72
    ),
    "pullback-buyer": BacktestSpec(
        "pullback-buyer", 0.042, 0.152, 0.55, 0.71, -0.215, 0.46, 1.12, 210
    ),
}

BT_START = date(2024, 7, 1)
BT_END = date(2026, 6, 30)
# One SPY buy-&-hold benchmark, shared by every backtest (~9%/yr over the window).
SPY_ANNUAL_RETURN = 0.09


def stable_rng(key: str) -> random.Random:
    """Deterministic RNG seeded from a stable SHA-256 of ``key`` (not ``hash``,
    whose salt varies run-to-run) — matches the ``price_at`` determinism note."""
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big"))


def event_id_for(key: str) -> UUID:
    """Deterministic ledger ``event_id`` from a stable key — identical derivation
    to the real ingestion ``_event_id_from_client_order_id`` (sha256[:16]). Fills
    key on ``client_order_id`` and reservations on ``client_order_id:stage`` so a
    seeded event carries the SAME identity production would, and re-seeds are
    byte-stable instead of minting fresh ``uuid4`` ids each run."""
    return UUID(bytes=hashlib.sha256(key.encode()).digest()[:16])


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


def bt_trading_days() -> list[date]:
    """Mon-Fri sessions across the backtest window (daily equity grid)."""
    days: list[date] = []
    d = BT_START
    while d <= BT_END:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


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


class Seeder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.writer = LedgerWriter(db)
        self.counts: dict[str, int] = {}
        self.seed_events: list[SeedEvent] = []
        self._seq = 0
        self._order_plan: dict[UUID, str] = {}

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
            "DELETE FROM agent_memory_embeddings WHERE tenant_id = :t",
            "DELETE FROM agent_session_summaries WHERE tenant_id = :t",
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
            created_at=dt(DEPOSIT_DAY, 9, 0),
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
            last_login=dt(TODAY - timedelta(days=1), 8, 15),
            settings={"default_view": "dashboard"},
            created_at=dt(DEPOSIT_DAY, 9, 0),
        )
        self.db.add(self.user)
        await self.db.flush()
        self.user_id = self.user.id
        self._bump("users")

        self.creds = AlpacaCredentials(
            id=uuid4(),
            tenant_id=self.tenant_id,
            name="Alpaca Paper (Demo)",
            api_key_encrypted=encrypt_value("PKDEMOALEXRIVERA0001"),
            api_secret_encrypted=encrypt_value("demoSecretAlexRivera00000000000000000001"),
            is_paper=True,
            is_active=True,
            created_at=dt(DEPOSIT_DAY, 9, 30),
        )
        self.db.add(self.creds)
        await self.db.flush()
        self.credentials_id = self.creds.id
        self._bump("alpaca_credentials")

    # billing

    async def seed_billing(self) -> None:
        pro = await self._get_or_create_plan(
            name="pro",
            display_name="Pro",
            description="For serious individual traders: unlimited strategies, live paper trading, AI copilot.",
            tier=billing_pb2.PLAN_TIER_PRO,
            price_monthly=Decimal("49.00"),
            price_yearly=Decimal("490.00"),
            features={"live_paper": True, "ai_copilot": True, "backtests": True},
            # Keys must match billing_service DEFAULT_PLANS: the servicer reads
            # limits["live_strategies"] for BOTH max_strategies and max_live_sessions
            # (services/billing/src/grpc/servicer.py). "strategies"/"live_sessions"
            # went over the wire as 0.
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

        sub = Subscription(
            id=uuid4(),
            tenant_id=self.tenant_id,
            plan_id=pro.id,
            status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
            billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
            stripe_subscription_id="sub_demo_alexrivera",
            stripe_customer_id="cus_demo_alexrivera",
            current_period_start=dt(date(2026, 7, 1), 0, 0),
            current_period_end=dt(date(2026, 8, 1), 0, 0),
            cancel_at_period_end=False,
            trial_start=dt(DEPOSIT_DAY, 0, 0),
            trial_end=dt(DEPOSIT_DAY + timedelta(days=14), 0, 0),
            created_at=dt(DEPOSIT_DAY, 9, 45),
        )
        self.db.add(sub)
        await self.db.flush()
        self.subscription_id = sub.id
        self._bump("subscriptions")

        self.db.add(
            PaymentMethod(
                id=uuid4(),
                tenant_id=self.tenant_id,
                stripe_payment_method_id="pm_demo_alexrivera_visa",
                stripe_customer_id="cus_demo_alexrivera",
                type="card",
                card_brand="visa",
                card_last4="4242",
                card_exp_month=11,
                card_exp_year=2028,
                is_default=True,
                created_at=dt(DEPOSIT_DAY, 9, 45),
            )
        )
        self._bump("payment_methods")

        # Paid monthly invoices Feb-Jul; Feb is the prorated Free->Pro upgrade.
        monthly_invoices: list[tuple[int, str, Decimal]] = [
            (2, "Free → Pro upgrade (prorated)", Decimal("31.60")),
            (3, "Pro plan (monthly)", Decimal("49.00")),
            (4, "Pro plan (monthly)", Decimal("49.00")),
            (5, "Pro plan (monthly)", Decimal("49.00")),
            (6, "Pro plan (monthly)", Decimal("49.00")),
            (7, "Pro plan (monthly)", Decimal("49.00")),
        ]
        for i, (month, desc, amount) in enumerate(monthly_invoices):
            self.db.add(
                Invoice(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    subscription_id=sub.id,
                    stripe_invoice_id=f"in_demo_alexrivera_2026{month:02d}",
                    invoice_number=f"LT-2026-{100 + i}",
                    status=billing_pb2.INVOICE_STATUS_PAID,
                    amount_due=amount,
                    amount_paid=amount,
                    currency="usd",
                    period_start=dt(date(2026, month, 14), 0, 0),
                    period_end=dt(date(2026, month + 1, 14), 0, 0),
                    paid_at=dt(date(2026, month, 14), 6, 5),
                    line_items=[{"description": desc, "amount": str(amount)}],
                    created_at=dt(date(2026, month, 14), 6, 0),
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

    def _load_strategy_data(self) -> dict[str, dict[str, object]]:
        raw = json.loads((DATA_DIR / "strategies.json").read_text())
        return {row["id"]: row for row in raw}

    async def seed_strategies(self) -> None:
        self.strategy_data = self._load_strategy_data()
        self.strategy_rows: dict[str, Strategy] = {}
        # Which template ids get a Strategy row (all 6) and which are "live".
        live_ids = {p.strategy_id for p in SLEEVE_PLANS if p.live}
        order = [
            "classic-60-40",
            "all-weather",
            "risk-parity",
            "momentum-sectors",
            "vigilant-asset-allocation",
            "pullback-buyer",
        ]
        created_days = {
            "classic-60-40": date(2026, 1, 8),
            "all-weather": date(2026, 1, 10),
            "risk-parity": date(2026, 1, 11),
            "momentum-sectors": date(2026, 1, 18),
            "vigilant-asset-allocation": date(2026, 3, 2),
            "pullback-buyer": date(2026, 4, 6),
        }
        for sid in order:
            data = self.strategy_data[sid]
            is_live = sid in live_ids
            # "vigilant-asset-allocation" is a built-but-paused strategy.
            if is_live:
                status = strategy_pb2.STRATEGY_STATUS_ACTIVE
            elif sid == "vigilant-asset-allocation":
                status = strategy_pb2.STRATEGY_STATUS_PAUSED
            else:
                status = strategy_pb2.STRATEGY_STATUS_DRAFT
            created = dt(created_days[sid], 11, 0)
            strat = Strategy(
                id=uuid4(),
                tenant_id=self.tenant_id,
                name=str(data["name"]),
                description=str(data["description"]),
                status=status,
                is_public=False,
                current_version=1,
                created_by=self.user_id,
                created_at=created,
            )
            self.db.add(strat)
            await self.db.flush()
            self.strategy_rows[sid] = strat
            self._bump("strategies")

            self.db.add(
                StrategyVersion(
                    id=uuid4(),
                    tenant_id=self.tenant_id,
                    strategy_id=strat.id,
                    version=1,
                    config_sexpr=str(data["config_sexpr"]),
                    config_json=data["config_json"],  # type: ignore[arg-type]
                    symbols=data["symbols"],  # type: ignore[arg-type]
                    timeframe=str(data["timeframe"]),
                    parameters={},
                    changelog="Initial version",
                    created_by=self.user_id,
                    created_at=created,
                )
            )
            self._bump("strategy_versions")

    # executions + ledger identity

    async def seed_executions_and_ledger_identity(self) -> None:
        """Create funded executions for live sleeves, then the ledger account +
        sleeves, then back-fill the ledger-identity trio onto each execution."""
        self.account = Account(
            id=uuid4(),
            tenant_id=self.tenant_id,
            credentials_id=self.credentials_id,
            base_currency="USD",
            created_at=dt(DEPOSIT_DAY, 10, 0),
        )
        self.db.add(self.account)
        await self.db.flush()
        self.account_id = self.account.id
        self._bump("ledger_accounts")

        # Base sleeves.
        self.base_sleeves: dict[SleeveType, Sleeve] = {}
        for kind, name in (
            (SleeveType.UNALLOCATED, "Unallocated"),
            (SleeveType.MANUAL, "Manual"),
            (SleeveType.UNMANAGED, "Unmanaged"),
        ):
            sleeve = Sleeve(
                id=uuid4(),
                tenant_id=self.tenant_id,
                account_id=self.account_id,
                type=kind.value,
                status=SleeveStatus.ACTIVE.value,
                name=name,
                allocated_capital=ZERO,
                created_at=dt(DEPOSIT_DAY, 10, 0),
            )
            self.db.add(sleeve)
            self.base_sleeves[kind] = sleeve
        await self.db.flush()
        self.unallocated = self.base_sleeves[SleeveType.UNALLOCATED]

        # Per-plan sleeve + (for live strategy plans) a funded execution.
        self.plan_sleeve: dict[str, Sleeve] = {}
        self.plan_execution: dict[str, StrategyExecution] = {}
        self.plan_session: dict[str, TradingSession] = {}
        for plan in SLEEVE_PLANS:
            if plan.kind is SleeveType.MANUAL:
                self.plan_sleeve[plan.key] = self.base_sleeves[SleeveType.MANUAL]
                continue

            strat = self.strategy_rows[plan.strategy_id]
            execution = StrategyExecution(
                id=uuid4(),
                tenant_id=self.tenant_id,
                strategy_id=strat.id,
                version=1,
                mode=common_pb2.EXECUTION_MODE_PAPER,
                status=common_pb2.EXECUTION_STATUS_RUNNING,
                started_at=dt_naive(plan.alloc_day, 14, 0),
                allocated_capital=plan.allocated,
                color=plan.color,
                credentials_id=self.credentials_id,
                created_at=dt(plan.alloc_day, 13, 55),
            )
            self.db.add(execution)
            await self.db.flush()

            sleeve = Sleeve(
                id=uuid4(),
                tenant_id=self.tenant_id,
                account_id=self.account_id,
                type=SleeveType.STRATEGY.value,
                status=SleeveStatus.ACTIVE.value,
                name=plan.name,
                strategy_execution_id=execution.id,
                allocated_capital=plan.allocated,
                created_at=dt(plan.alloc_day, 14, 0),
            )
            self.db.add(sleeve)
            await self.db.flush()

            execution.sleeve_id = sleeve.id
            execution.account_id = self.account_id
            self.plan_sleeve[plan.key] = sleeve
            self.plan_execution[plan.key] = execution
            self._bump("strategy_executions")
            self._bump("ledger_sleeves")

        self._bump("ledger_sleeves", 3)  # base sleeves

    # ledger events

    async def _append(
        self,
        event_type: LedgerEventType,
        data: dict[str, str],
        *,
        sleeve_id: UUID | None,
        occurred_at: datetime,
        event_id: UUID | None = None,
    ) -> None:
        event = await self.writer.append(
            tenant_id=self.tenant_id,
            account_id=self.account_id,
            event_type=event_type,
            data=data,
            sleeve_id=sleeve_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )
        # ``sequence`` is the DB-assigned global serial — the real ledger position,
        # which flows into each SleeveSnapshot.as_of_sequence. ``_seq`` stays a
        # local monotonic counter used only for FIFO lot ordering.
        self._seq += 1
        self.seed_events.append(
            SeedEvent(event_type.value, dict(data), int(event.sequence), occurred_at)
        )
        self._bump("ledger_events")

    def _coid(self, plan_key: str, n: int) -> str:
        return f"lt-demo-{plan_key}-{n:03d}"

    async def seed_ledger_events(self) -> None:
        # 1. Deposit into Unallocated.
        await self._append(
            LedgerEventType.FUNDS_DEPOSITED,
            {"sleeve_id": str(self.unallocated.id), "amount": str(INITIAL_DEPOSIT)},
            sleeve_id=self.unallocated.id,
            occurred_at=dt(DEPOSIT_DAY, 10, 5),
            event_id=event_id_for("demo:deposit"),
        )

        # 2. Allocations (chronological).
        for plan in sorted(SLEEVE_PLANS, key=lambda p: p.alloc_day):
            sleeve = self.plan_sleeve[plan.key]
            await self._append(
                LedgerEventType.CAPITAL_ALLOCATED,
                {
                    "from_sleeve_id": str(self.unallocated.id),
                    "to_sleeve_id": str(sleeve.id),
                    "amount": str(plan.allocated),
                },
                sleeve_id=sleeve.id,
                occurred_at=dt(plan.alloc_day, 14, 1),
                event_id=event_id_for(f"demo:alloc:{plan.key}"),
            )

        # 3. Fills + dividends, all in global chronological order.
        self.order_rows: list[Order] = []
        # Per-(sleeve, symbol) position accounting captured off the fill stream, so
        # ``seed_positions`` can materialize the ``positions`` table (which the
        # ledger fold does not feed) from the same lots that explain the fills.
        self.pos_realized: dict[tuple[str, str], Decimal] = {}
        self.pos_opened: dict[tuple[str, str], datetime] = {}
        lots: dict[tuple[str, str], list[FifoLot]] = {}
        fill_counter: dict[str, int] = {}

        timeline: list[tuple[date, str, object]] = []
        for plan in SLEEVE_PLANS:
            for f in plan.fills:
                timeline.append((f.day, plan.key, f))
        for key, day, symbol, amount in DIVIDENDS:
            timeline.append((day, key, ("dividend", symbol, amount)))
        timeline.sort(key=lambda row: (row[0], row[1]))

        for day, plan_key, payload in timeline:
            plan = next(p for p in SLEEVE_PLANS if p.key == plan_key)
            sleeve = self.plan_sleeve[plan_key]
            if isinstance(payload, Fill):
                await self._append_fill(plan, sleeve, payload, lots, fill_counter)
            else:
                _, symbol, amount = payload  # type: ignore[misc]
                await self._append(
                    LedgerEventType.DIVIDEND_RECEIVED,
                    {"sleeve_id": str(sleeve.id), "amount": str(amount), "symbol": str(symbol)},
                    sleeve_id=sleeve.id,
                    occurred_at=dt(day, 12, 0),
                    event_id=event_id_for(f"demo:div:{plan_key}:{symbol}:{day.isoformat()}"),
                )

        self.final_lots = lots

    async def _append_fill(
        self,
        plan: SleevePlan,
        sleeve: Sleeve,
        fill: Fill,
        lots: dict[tuple[str, str], list[FifoLot]],
        fill_counter: dict[str, int],
    ) -> None:
        key = (str(sleeve.id), fill.symbol)
        n = fill_counter.get(plan.key, 0) + 1
        fill_counter[plan.key] = n
        client_order_id = self._coid(plan.key, n)
        order_id = uuid4()
        notional = (fill.qty * fill.price).quantize(CENT)

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
            # Reservation lifecycle (§4): a buy earmarks cash before it fills. The
            # ORDER_SUBMITTED carries no economic postings; the ORDER_FILLED below
            # (same client_order_id) releases the reservation — mirroring the real
            # trading→ledger flow, which the seed otherwise never exercises.
            await self._append(
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
                occurred_at=dt(fill.day, 14, 29),
                event_id=event_id_for(f"{client_order_id}:order_submitted"),
            )
            lots.setdefault(key, []).append(
                FifoLot(qty=fill.qty, cost_basis=notional, opened_seq=self._seq + 1)
            )
            self.pos_opened.setdefault(key, dt(fill.day, 14, 30))
        else:  # sell — resolve FIFO cost basis with the real kernel selector
            open_lots = lots.get(key, [])
            result = select_lots_fifo(open_lots, fill.qty)
            lots[key] = result.remaining_lots
            cost = result.closed_cost_basis.quantize(CENT)
            realized = (notional - cost - fill.fees).quantize(CENT)
            data["cost_basis"] = str(cost)
            data["realized_pnl"] = str(realized)
            self.pos_realized[key] = self.pos_realized.get(key, ZERO) + realized

        await self._append(
            LedgerEventType.ORDER_FILLED,
            data,
            sleeve_id=sleeve.id,
            occurred_at=dt(fill.day, 14, 30),
            event_id=event_id_for(client_order_id),
        )

        # Trading Order row (only for live strategy sleeves; Manual lives in the ledger).
        if plan.live:
            self.order_rows.append(self._make_order(plan, sleeve, fill, order_id, client_order_id))
            self._order_plan[order_id] = plan.key

    def _make_order(
        self, plan: SleevePlan, sleeve: Sleeve, fill: Fill, order_id: UUID, client_order_id: str
    ) -> Order:
        order = Order(
            id=order_id,
            tenant_id=self.tenant_id,
            alpaca_order_id=f"demo-{client_order_id}",
            client_order_id=client_order_id,
            symbol=fill.symbol,
            side=trading_pb2.ORDER_SIDE_BUY if fill.side == "buy" else trading_pb2.ORDER_SIDE_SELL,
            order_type=trading_pb2.ORDER_TYPE_MARKET,
            time_in_force=trading_pb2.TIME_IN_FORCE_DAY,
            qty=fill.qty,
            status=trading_pb2.ORDER_STATUS_FILLED,
            filled_qty=fill.qty,
            filled_avg_price=fill.price,
            submitted_at=dt(fill.day, 14, 29),
            filled_at=dt(fill.day, 14, 30),
            signal_reason=(
                "Rebalance to target weights"
                if fill.day > plan.alloc_day + timedelta(days=7)
                else "Initial allocation"
            ),
            metadata_={"source": "demo_seed", "mode": "paper"},
            sleeve_id=sleeve.id,
            account_id=self.account_id,
            created_at=dt(fill.day, 14, 29),
        )
        return order

    # trading rows

    async def seed_trading(self) -> None:
        for plan in SLEEVE_PLANS:
            if not plan.live:
                continue
            sleeve = self.plan_sleeve[plan.key]
            strat = self.strategy_rows[plan.strategy_id]
            symbols = list(self.strategy_data[plan.strategy_id]["symbols"])  # type: ignore[arg-type]
            session = TradingSession(
                id=uuid4(),
                tenant_id=self.tenant_id,
                strategy_id=strat.id,
                strategy_version=1,
                credentials_id=self.credentials_id,
                name=f"{plan.name} (paper)",
                mode=common_pb2.EXECUTION_MODE_PAPER,
                status=common_pb2.EXECUTION_STATUS_RUNNING,  # → 'active'
                config={"drift_tolerance": "0.05"},
                symbols=symbols,
                started_at=dt(plan.alloc_day, 14, 0),
                last_heartbeat=dt(TODAY, 15, 0),
                created_by=self.user_id,
                sleeve_id=sleeve.id,
                account_id=self.account_id,
                created_at=dt(plan.alloc_day, 14, 0),
            )
            self.db.add(session)
            await self.db.flush()
            self.plan_session[plan.key] = session
            self._bump("trading_sessions")

        # Attach orders to their sessions.
        for order in self.order_rows:
            plan_key = self._order_plan[order.id]
            order.session_id = self.plan_session[plan_key].id
            self.db.add(order)
            self._bump("orders")
        await self.db.flush()

        await self.seed_positions()

    async def seed_positions(self) -> None:
        """Open positions per live session — the ``positions`` table backing the
        Trading page's ``ListPositions`` (which the ledger fold does NOT feed).
        qty/cost basis come from the same FIFO lots that explain the fills, marked
        to today's price so the page shows live P&L. A fully-exited live symbol (or
        the Manual sleeve, which has no session) stays ledger-only — the Trading
        page lists open positions. These mirror the folded sleeve position exactly."""
        for plan in SLEEVE_PLANS:
            if not plan.live:
                continue
            session = self.plan_session[plan.key]
            sleeve_key = str(self.plan_sleeve[plan.key].id)
            for (lot_sleeve, symbol), open_lots in self.final_lots.items():
                if lot_sleeve != sleeve_key:
                    continue
                qty = sum((lot.qty for lot in open_lots), ZERO)
                if qty <= ZERO:
                    continue  # fully exited → realized in the ledger, no open row
                cost_basis = sum((lot.cost_basis for lot in open_lots), ZERO).quantize(CENT)
                avg_entry = (cost_basis / qty).quantize(Decimal("0.00000001"))
                mark = price_at(symbol, TODAY)
                market_value = (qty * mark).quantize(CENT)
                unrealized = (market_value - cost_basis).quantize(CENT)
                unrealized_pct = (
                    (unrealized / cost_basis).quantize(Decimal("0.000001")) if cost_basis else ZERO
                )
                opened_at = self.pos_opened.get((sleeve_key, symbol), session.started_at)
                self.db.add(
                    Position(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        session_id=session.id,
                        symbol=symbol,
                        side=trading_pb2.POSITION_SIDE_LONG,
                        qty=qty,
                        avg_entry_price=avg_entry,
                        current_price=mark,
                        market_value=market_value,
                        cost_basis=cost_basis,
                        unrealized_pl=unrealized,
                        unrealized_plpc=unrealized_pct,
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
        """Equity-curve snapshots folded from the constructed event stream and
        marked with the real ``compute_snapshot_values`` kernel — one per sleeve
        per calendar day across the whole history, so the equity curve is dense
        and day-P&L has a true 1-day baseline. Stops at ``TODAY - 1``: today's
        close is the live mark (today's market-data bar, seeded in
        ``seed_market_bars``), so day-P&L is a real one-session move, not zero.
        ``as_of_sequence`` carries the real ledger sequence of the latest event
        as of each day (the read layer keys the curve off ``created_at`` day, so
        shared sequences on quiet days never collapse the daily points)."""
        from src.ledger.projection import fold

        all_symbols = sorted(PRICE_PATH)
        snapshot_days: list[date] = []
        d = DEPOSIT_DAY
        while d < TODAY:  # today's close is the live mark, not a snapshot
            snapshot_days.append(d)
            d += timedelta(days=1)

        for d in snapshot_days:
            events_upto = [e for e in self.seed_events if e.occurred_at.date() <= d]
            if not events_upto:
                continue
            projection = fold(events_upto)  # type: ignore[arg-type]
            prices = {s: price_at(s, d) for s in all_symbols}
            seq = events_upto[-1].sequence
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
                        created_at=dt(d, 16, 0),
                    )
                )
                self._bump("ledger_sleeve_snapshots")

    # market-data bars

    async def seed_market_bars(self) -> None:
        """Daily OHLCV bars in the market-data Timescale store so open positions
        mark to market. The portfolio prices live positions via the market-data
        snapshot endpoint, which — with no Alpaca feed in the demo — falls back to
        the newest stored daily bar's close. Bars follow the same ``price_at``
        path as the equity snapshots, so the live mark continues the historical
        curve smoothly (no cliff). Idempotent: upsert keyed on ``(symbol, time)``."""
        symbols = sorted(PRICE_PATH)
        rows: list[dict[str, object]] = []
        fetched = dt(TODAY, 20, 5)
        for symbol in symbols:
            d = BARS_START
            while d <= TODAY:
                if d.weekday() < 5:  # trading sessions only
                    close = price_at(symbol, d)
                    open_ = price_at(symbol, d - timedelta(days=1))
                    high = (max(open_, close) * Decimal("1.004")).quantize(CENT)
                    low = (min(open_, close) * Decimal("0.996")).quantize(CENT)
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
                d += timedelta(days=1)

        engine = create_async_engine(MARKET_DATA_DB_URL)
        try:
            async with engine.begin() as conn:
                for i in range(0, len(rows), 500):
                    chunk = rows[i : i + 500]
                    stmt = pg_insert(BARS_DAILY).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["symbol", "time"],
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "vwap": stmt.excluded.vwap,
                            "trade_count": stmt.excluded.trade_count,
                            "adjustment": stmt.excluded.adjustment,
                            "fetched_at": stmt.excluded.fetched_at,
                        },
                    )
                    await conn.execute(stmt)
        finally:
            await engine.dispose()
        self._bump("market_data_bars", len(rows))

    # backtests

    async def seed_backtests(self) -> None:
        """Completed 2Y backtests whose stored metrics are DERIVED from the same
        synthesized curve/trades a real engine run would (metrics.py + _persist),
        so nothing contradicts (e.g. a negative curve can't carry a positive
        CAGR). One shared SPY buy-&-hold benchmark backs every run's SPY number
        and CAPM alpha/beta/IR."""
        days = bt_trading_days()
        initial = 100000.0
        # One SPY buy-&-hold series shared by ALL backtests (same number, same
        # overlay grid) — not a per-strategy re-randomized benchmark.
        spy_bars, benchmark_curve, benchmark_return, spy_lr = self._synth_benchmark(days)

        for sid, strat in self.strategy_rows.items():
            spec = BACKTEST_SPECS[sid]
            symbols = list(self.strategy_data[sid]["symbols"])  # type: ignore[arg-type]

            curve, curve_points, equity = self._synth_curve(spec, days, spy_lr)
            num_days = len(equity)
            total_return, annual_return, daily_returns = bt_returns(equity, initial, num_days)
            daily_arr = np.array(daily_returns)
            eq_arr = np.array(equity, dtype=float)
            sharpe = bt_sharpe(daily_arr)
            sortino = bt_sortino(daily_arr)
            max_dd_pos, dd_duration = bt_max_drawdown(eq_arr)
            monthly = bt_monthly_returns(curve_points, initial)
            final_equity = float(eq_arr[-1])

            # Trades sum EXACTLY to the curve's gain, so Σ(trade pnl) == final_equity − initial.
            st = self._synth_trades(spec, symbols, final_equity - initial)

            # Alpha / beta / information ratio from the ONE shared SPY series (CAPM,
            # date-joined daily returns) — not independent randoms.
            strat_ret, bench_ret = bt_align_daily_returns(curve_points, spy_bars)
            alpha, beta = bt_alpha_beta(strat_ret, bench_ret)
            info_ratio = bt_information_ratio(strat_ret, bench_ret)

            bt = Backtest(
                id=uuid4(),
                tenant_id=self.tenant_id,
                strategy_id=strat.id,
                strategy_version=1,
                name=f"{strat.name} — 2Y backtest",
                status=backtest_pb2.BACKTEST_STATUS_COMPLETED,
                # Engine's config shape (BacktestService.create_backtest). Curve is
                # daily-resampled regardless of strategy timeframe, so store "1D".
                config={
                    "commission": 0.0,
                    "slippage": 0.0,
                    "timeframe": "1D",
                    "benchmark_symbol": "SPY",
                    "include_benchmark": True,
                },
                symbols=symbols,
                start_date=BT_START,
                end_date=BT_END,
                initial_capital=Decimal("100000.00"),
                started_at=dt(strat.created_at.date(), 12, 0),
                completed_at=dt(strat.created_at.date(), 12, 4),
                created_by=self.user_id,
                created_at=dt(strat.created_at.date(), 12, 0),
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
                    sharpe_ratio=Decimal(str(round(sharpe, 4))),
                    sortino_ratio=Decimal(str(round(sortino, 4))),
                    # Stored NEGATIVE (magnitude from the curve). The engine stores
                    # a positive drawdown fraction, but the current UI renders the
                    # negative/fraction convention correctly, so we keep it.
                    max_drawdown=Decimal(str(round(-max_dd_pos, 6))),
                    max_drawdown_duration=dd_duration,  # trading days (engine convention)
                    win_rate=Decimal(str(round(st.win_rate, 4))),
                    profit_factor=Decimal(str(round(st.profit_factor, 4)))
                    if st.profit_factor is not None
                    else None,
                    exposure_time=Decimal(
                        str(round(stable_rng(sid + ":exposure").uniform(92.0, 99.9), 2))
                    ),
                    total_trades=st.total,
                    winning_trades=st.winning,
                    losing_trades=st.losing,
                    avg_trade_return=Decimal(str(round(st.avg_trade_return, 6))),
                    final_equity=Decimal(str(round(final_equity, 2))),
                    equity_curve=curve,
                    trades=st.trades,
                    daily_returns=[round(r, 8) for r in daily_returns],
                    monthly_returns={k: round(v, 6) for k, v in monthly.items()},
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

    def _synth_benchmark(
        self, days: list[date]
    ) -> tuple[list[tuple[datetime, float]], list[dict[str, object]], float, list[float]]:
        """One deterministic SPY close path over the window → buy-&-hold curve +
        return (benchmarks.calculate_spy_buy_hold), shared by every backtest.
        Log-returns are re-centered to a realistic ~9%/yr so the SPY number is
        sensible rather than a random walk that could end anywhere. Returns the
        SPY log-returns too, so each strategy path can load on the market and
        produce realistic betas."""
        rng = stable_rng("SPY-benchmark")
        sigma = 0.14 / math.sqrt(252.0)
        n = len(days)
        lr = [rng.gauss(0.0, sigma) for _ in range(n - 1)]
        target_log = (n / 252.0) * math.log1p(SPY_ANNUAL_RETURN)
        if n > 1:
            adj = (target_log - sum(lr)) / (n - 1)
            lr = [x + adj for x in lr]
        closes = [500.0]
        cum = 0.0
        for x in lr:
            cum += x
            closes.append(500.0 * math.exp(cum))
        spy_bars = [(dt(days[i], 21, 0), closes[i]) for i in range(n)]
        shares = 100000.0 / closes[0]
        curve: list[dict[str, object]] = [
            {"date": ts.isoformat(), "equity": round(shares * close, 2)} for ts, close in spy_bars
        ]
        benchmark_return = (shares * closes[-1] - 100000.0) / 100000.0
        return spy_bars, curve, benchmark_return, lr

    def _synth_curve(
        self, spec: BacktestSpec, days: list[date], spy_lr: list[float]
    ) -> tuple[list[dict[str, object]], list[tuple[datetime, float]], list[float]]:
        """Daily equity path whose log-returns are re-centered to hit exactly
        ``spec.ann_return`` annualized (num_days = len(curve)): the stored
        annual_return then recovers ``spec.ann_return`` and is sign-consistent
        with the curve — no hardcoded-CAGR-vs-negative-curve contradiction. Each
        return loads on the shared SPY series (market beta ≈ ``0.7·vol/0.14``,
        capped) plus idiosyncratic noise sized so total vol ≈ ``spec.ann_vol``,
        giving realistic CAPM betas while sharpe/drawdown stay derived from the
        path. Full datetime+tz date strings; one point per trading day."""
        rng = stable_rng(spec.strategy_id)
        sigma_spy = 0.14 / math.sqrt(252.0)
        sigma_strat = spec.ann_vol / math.sqrt(252.0)
        # Market loading ≈ target beta; idiosyncratic variance makes up the rest so
        # var(beta·spy + idio) ≈ var(strat). ``0.7·vol/0.14`` keeps low-vol sleeves
        # from claiming an impossibly high beta to the 14%-vol index.
        beta_target = min(0.9, 0.7 * spec.ann_vol / 0.14)
        sigma_idio = math.sqrt(max(sigma_strat**2 - (beta_target * sigma_spy) ** 2, 0.0))
        n = len(days)
        lr = [beta_target * spy_lr[i] + rng.gauss(0.0, sigma_idio) for i in range(n - 1)]
        target_log = (n / 252.0) * math.log1p(spec.ann_return)
        if n > 1:
            adj = (target_log - sum(lr)) / (n - 1)
            lr = [x + adj for x in lr]
        equity = [100000.0]
        cum = 0.0
        for x in lr:
            cum += x
            equity.append(100000.0 * math.exp(cum))
        curve_points = [(dt(days[i], 21, 0), equity[i]) for i in range(n)]
        curve: list[dict[str, object]] = [
            {"date": ts.isoformat(), "equity": round(eq, 2)} for ts, eq in curve_points
        ]
        return curve, curve_points, equity

    def _synth_trades(
        self, spec: BacktestSpec, symbols: list[str], target_pnl: float
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

        span = (BT_END - BT_START).days
        raw: list[_RawTrade] = []
        for i, is_win in enumerate(flags):
            entry = round(rng.uniform(40, 320), 2)
            qty = rng.randint(5, 60)
            pct = rng.uniform(0.005, 0.09) if is_win else -rng.uniform(0.005, 0.07)
            entry_day = BT_START + timedelta(days=rng.randint(0, max(1, span - 10)))
            exit_day = min(entry_day + timedelta(days=rng.randint(3, 40)), BT_END)
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
        # (there is no ``create_strategy`` tool) and, on success, persists a
        # PENDING strategy artifact as a side effect. Reproduce that instead of a
        # fabricated tool call with no backing artifact.
        mom = self.strategy_data["momentum-sectors"]
        mom_dsl = str(mom["config_sexpr"])
        mom_symbols = list(mom["symbols"])  # type: ignore[arg-type]
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
                    "rebalance_frequency": "monthly",
                    "benchmark": "SPY",
                    "symbols": mom_symbols,
                    "indicators": ["momentum"],
                },
                "duration_ms": 38,
                "success": True,
            }
        ]
        sessions = [
            {
                "title": "Build a momentum sector strategy",
                "status": agent_pb2.AGENT_SESSION_STATUS_COMPLETED,
                "day": date(2026, 1, 17),
                "messages": [
                    (
                        "user",
                        "I want a strategy that rotates into the strongest market sectors each month. Can you help me build one?",
                        None,
                    ),
                    (
                        "assistant",
                        "Absolutely. A sector-momentum rotation ranks the 11 S&P sector ETFs by trailing 3-month return and overweights the leaders, rebalancing monthly. I'll split it into cyclical, defensive, and commodity sectors and pick the top performers in each with a momentum filter. Want me to draft it?",
                        None,
                    ),
                    (
                        "user",
                        "Yes, draft it and keep it diversified so I'm not all-in on tech.",
                        None,
                    ),
                    (
                        "assistant",
                        "Done — I've drafted **Momentum Sectors** and validated it. It holds the top 3 cyclical sectors, top 2 defensive, and momentum-weights the commodity sectors, rebalanced monthly. Backtest shows ~11.5% CAGR with a deeper drawdown (~-20%), which is typical for momentum. Review it below, then save it to your strategies and fund it from the Strategies page.",
                        momentum_validate_call,
                    ),
                ],
                "summary": (
                    "Built a monthly sector-momentum rotation strategy (Momentum Sectors), diversified across cyclical/defensive/commodity sectors.",
                    "User wanted a diversified monthly sector-rotation strategy that avoids concentration in tech. Drafted Momentum Sectors using a top-N momentum filter per sector group; discussed the higher-drawdown tradeoff of momentum.",
                    ["momentum", "sector rotation", "diversification"],
                    ["Momentum Sectors"],
                    [
                        "Chose top-3 cyclical / top-2 defensive with momentum weighting",
                        "Rebalance monthly",
                    ],
                ),
            },
            {
                "title": "Why did Risk Parity draw down in April?",
                "status": agent_pb2.AGENT_SESSION_STATUS_COMPLETED,
                "day": date(2026, 4, 22),
                "messages": [
                    ("user", "My Risk Parity sleeve dipped in April. What happened?", None),
                    (
                        "assistant",
                        "The drawdown came from the long-bond leg: TLT fell ~3% as yields backed up, and that's your largest risk-weighted position. Gold (GLD) offset some of it (+9% YTD). Risk parity is working as designed — the bond drag was cushioned by the diversifiers. No action needed unless your risk tolerance changed.",
                        None,
                    ),
                    (
                        "user",
                        "Got it, I'm comfortable holding. Keep max drawdown under about 15% though.",
                        None,
                    ),
                    (
                        "assistant",
                        "Noted — I'll keep an eye on the sleeve and flag it if projected drawdown approaches 15%.",
                        None,
                    ),
                ],
                "summary": (
                    "Explained the April Risk Parity drawdown (long-bond weakness, partially offset by gold); user confirmed a ~15% max-drawdown comfort level.",
                    "User asked why the Risk Parity sleeve drew down in April. Attributed it to TLT weakness offset by GLD strength; reassured that risk parity behaved as designed. User set a ~15% max-drawdown tolerance.",
                    ["risk parity", "drawdown", "bonds", "gold"],
                    ["Risk Parity"],
                    ["Hold the Risk Parity sleeve", "Keep max drawdown under ~15%"],
                ),
            },
            {
                "title": "What is dual momentum?",
                "status": agent_pb2.AGENT_SESSION_STATUS_ACTIVE,
                "day": date(2026, 7, 10),
                "messages": [
                    (
                        "user",
                        "What's the difference between dual momentum and my current momentum strategy?",
                        None,
                    ),
                    (
                        "assistant",
                        "Dual momentum combines **relative** momentum (pick the strongest asset among several) with **absolute** momentum (only hold it if it's also beating cash/T-bills). If nothing has positive absolute momentum, it moves to bonds or cash — a built-in defensive switch. Your Momentum Sectors uses relative momentum only, so it stays invested even in downturns. Want me to sketch a dual-momentum version like the Vigilant Asset Allocation template?",
                        None,
                    ),
                ],
                "summary": None,
            },
        ]

        momentum_session_id: UUID | None = None
        for s in sessions:
            msgs = s["messages"]
            session = AgentSession(
                id=uuid4(),
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                title=str(s["title"]),
                status=s["status"],  # type: ignore[arg-type]
                message_count=len(msgs),  # type: ignore[arg-type]
                last_activity_at=dt(s["day"], 16, 0),  # type: ignore[arg-type]
                created_at=dt(s["day"], 15, 30),  # type: ignore[arg-type]
            )
            self.db.add(session)
            await self.db.flush()
            self._bump("agent_sessions")
            if s["title"] == "Build a momentum sector strategy":
                momentum_session_id = session.id

            for i, (role, content, tool_calls) in enumerate(msgs):  # type: ignore[arg-type]
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
                        created_at=dt(s["day"], 15, 30) + timedelta(minutes=i),  # type: ignore[arg-type]
                    )
                )
                self._bump("agent_messages")

            summary = s["summary"]
            if summary is not None:
                short, detailed, topics, strategies_discussed, decisions = summary  # type: ignore[misc]
                self.db.add(
                    AgentSessionSummary(
                        id=uuid4(),
                        tenant_id=self.tenant_id,
                        user_id=self.user_id,
                        session_id=session.id,
                        summary_short=short,
                        summary_detailed=detailed,
                        topics=topics,
                        strategies_discussed=strategies_discussed,
                        decisions=decisions,
                        message_count_at_summary=len(msgs),  # type: ignore[arg-type]
                        created_at=dt(s["day"], 16, 5),  # type: ignore[arg-type]
                    )
                )
                self._bump("agent_session_summaries")

        # Backing pending artifact for the Momentum Sectors turn (the side effect
        # of the validate_dsl call above). artifact_json matches ArtifactService.
        # create_strategy_artifact; left UNCOMMITTED so GetSession surfaces it
        # (get_pending_artifacts filters committed rows out by default).
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
                        "config_json": mom["config_json"],
                        "symbols": mom_symbols,
                        "timeframe": str(mom["timeframe"]),
                    },
                    is_committed=False,
                    created_at=dt(date(2026, 1, 17), 15, 33),
                )
            )
            self._bump("pending_artifacts")

        # Cross-session memory facts.
        facts = [
            (
                "risk_tolerance",
                "Moderate risk tolerance; comfortable with drawdowns up to ~15%.",
                0.9,
            ),
            (
                "asset_preference",
                "Prefers broad, liquid ETFs; likes a tech tilt but wants diversification.",
                0.85,
            ),
            ("investment_goal", "Long-term growth, ~15 year horizon toward retirement.", 0.8),
            (
                "strategy_decision",
                "Runs a core-and-satellite mix: All-Weather + Risk Parity core, Momentum Sectors satellite.",
                0.88,
            ),
            (
                "trading_behavior",
                "Rebalances roughly monthly and reviews sleeves after notable moves.",
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
                    last_accessed_at=dt(TODAY - timedelta(days=2), 10, 0),
                    access_count=RNG.randint(1, 6),
                    created_at=dt(date(2026, 1, 20), 10, 0),
                )
            )
            self._bump("agent_memory_facts")

    # run

    async def run(self) -> None:
        await self.purge_existing()
        await self.seed_identity()
        await self.seed_billing()
        await self.seed_strategies()
        await self.seed_executions_and_ledger_identity()
        await self.seed_ledger_events()
        await self.seed_trading()
        await self.seed_snapshots()
        await self.seed_market_bars()
        await self.seed_backtests()
        await self.seed_agent()


async def main() -> None:
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
    logger.info("DEMO SEED COMPLETE")
    logger.info("  login: %s / %s", DEMO_EMAIL, DEMO_PASSWORD)
    logger.info("  tenant: %s (%s)", TENANT_NAME, DEMO_SLUG)
    for key in sorted(seeder.counts):
        logger.info("  %-26s %d", key, seeder.counts[key])
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
